#!/usr/bin/env bash
# Deploy, collect and remove the warm-container/cold-data probe on AWS Lambda.
#
# Run in AWS CloudShell, which already has the AWS CLI, python3 and your
# credentials, next to residency_probe.zip from build.sh:
#
#   ./deploy.sh deploy     one function per (memory, idle) cell, each invoked by
#                          its own fixed-rate EventBridge schedule
#   ./deploy.sh collect    every RESIDENCY record from CloudWatch Logs into
#                          residency_<utc>.csv (works before and after teardown)
#   ./deploy.sh stop       delete the schedules, so nothing is invoked any more
#   ./deploy.sh teardown   stop, then delete the functions, roles and bucket.
#                          Log groups are kept so collect still works.
#
# One function per cell rather than one function re-scheduled per cell: separate
# functions never share an execution environment, so all cells run at the same
# time without one cell's invocations keeping another cell's environment warm.
#
# Override the matrix with  MEMS="128 1024" IDLES="5 30" ./deploy.sh deploy
# (IDLES in minutes). Every cell is its own function, so a smaller matrix is
# just fewer functions, not a different experiment.
set -euo pipefail
shopt -s inherit_errexit
cd "$(dirname "$0")"

CMD="${1:-}"
case "$CMD" in deploy|collect|stop|teardown) ;; *)
  echo "usage: $0 deploy|collect|stop|teardown"; exit 2 ;;
esac

MEMS="${MEMS:-128 256 512 1024}"
IDLES="${IDLES:-1 5 15 30 60}"
ZIP="${ZIP:-residency_probe.zip}"
PREFIX=coldprobe
KEY=residency_probe.zip
LROLE="$PREFIX-lambda"
SROLE="$PREFIX-scheduler"
BASIC=arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole
export AWS_PAGER=""

REGION="${AWS_REGION:-$(aws configure get region || true)}"
[ -n "$REGION" ] || { echo "no AWS region: set AWS_REGION"; exit 1; }
ACCOUNT="$(aws sts get-caller-identity --query Account --output text)"
BUCKET="$PREFIX-$ACCOUNT-$REGION"

fname() { echo "$PREFIX-m$1-i$2"; }
rate()  { if [ "$1" = 1 ]; then echo "rate(1 minute)"; else echo "rate($1 minutes)"; fi; }

# A role is refused for a few seconds after it is created, until IAM propagates it.
retry() {
  local n
  for n in 1 2 3 4 5 6 7 8; do
    if "$@"; then return 0; fi
    echo "   not ready yet, retrying in 10 s ($n/8)" >&2
    sleep 10
  done
  return 1
}

ensure_role() {  # <name> <service principal>  -> prints the role ARN
  if ! aws iam get-role --role-name "$1" >/dev/null 2>&1; then
    aws iam create-role --role-name "$1" --assume-role-policy-document \
      "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Effect\":\"Allow\",\"Principal\":{\"Service\":\"$2\"},\"Action\":\"sts:AssumeRole\"}]}" >/dev/null
  fi
  aws iam get-role --role-name "$1" --query Role.Arn --output text
}

cmd_deploy() {
  [ -f "$ZIP" ] || { echo "missing $ZIP: upload it to CloudShell next to this script"; exit 1; }

  echo "== bucket $BUCKET"
  if ! aws s3api head-bucket --bucket "$BUCKET" >/dev/null 2>&1; then
    if [ "$REGION" = us-east-1 ]; then
      aws s3api create-bucket --bucket "$BUCKET" >/dev/null
    else
      aws s3api create-bucket --bucket "$BUCKET" \
        --create-bucket-configuration "LocationConstraint=$REGION" >/dev/null
    fi
  fi
  aws s3 cp "$ZIP" "s3://$BUCKET/$KEY" --only-show-errors

  echo "== roles"
  local larn sarn
  larn=$(ensure_role "$LROLE" lambda.amazonaws.com)
  aws iam attach-role-policy --role-name "$LROLE" --policy-arn "$BASIC"
  sarn=$(ensure_role "$SROLE" scheduler.amazonaws.com)
  aws iam put-role-policy --role-name "$SROLE" --policy-name invoke-probe --policy-document \
    "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Effect\":\"Allow\",\"Action\":\"lambda:InvokeFunction\",\"Resource\":\"arn:aws:lambda:$REGION:$ACCOUNT:function:$PREFIX-*\"}]}"

  local m i fn farn target
  for m in $MEMS; do
    for i in $IDLES; do
      fn=$(fname "$m" "$i")
      echo "== $fn   memory $m MB, $(rate "$i")"
      if aws lambda get-function --function-name "$fn" >/dev/null 2>&1; then
        aws lambda update-function-code --function-name "$fn" \
          --s3-bucket "$BUCKET" --s3-key "$KEY" >/dev/null
        aws lambda wait function-updated-v2 --function-name "$fn"
        aws lambda update-function-configuration --function-name "$fn" \
          --memory-size "$m" --timeout 60 --environment "Variables={IDLE_MIN=$i}" >/dev/null
        aws lambda wait function-updated-v2 --function-name "$fn"
      else
        # x86_64 to match the architecture of every local batch in the paper.
        retry aws lambda create-function --function-name "$fn" \
          --runtime python3.12 --architectures x86_64 \
          --handler lambda_function.lambda_handler --role "$larn" \
          --code "S3Bucket=$BUCKET,S3Key=$KEY" \
          --memory-size "$m" --timeout 60 --environment "Variables={IDLE_MIN=$i}" >/dev/null
        aws lambda wait function-active-v2 --function-name "$fn"
      fi

      # No retries: a retried invocation would land seconds after a failed one
      # and break the idle interval the cell exists to hold fixed.
      farn=$(aws lambda get-function --function-name "$fn" --query Configuration.FunctionArn --output text)
      target="{\"Arn\":\"$farn\",\"RoleArn\":\"$sarn\",\"Input\":\"{}\",\"RetryPolicy\":{\"MaximumRetryAttempts\":0}}"
      if aws scheduler get-schedule --name "$fn" >/dev/null 2>&1; then
        aws scheduler update-schedule --name "$fn" --schedule-expression "$(rate "$i")" \
          --flexible-time-window Mode=OFF --target "$target" >/dev/null
      else
        retry aws scheduler create-schedule --name "$fn" --schedule-expression "$(rate "$i")" \
          --flexible-time-window Mode=OFF --target "$target" >/dev/null
      fi
    done
  done
  echo "== deployed. Records accumulate in CloudWatch Logs; run './deploy.sh collect' any time."
}

cmd_collect() {
  local out lg
  out="residency_$(date -u +%Y%m%dT%H%M%SZ)"
  : > "$out.jsonl"
  for lg in $(aws logs describe-log-groups --log-group-name-prefix "/aws/lambda/$PREFIX-" \
                --query 'logGroups[].logGroupName' --output text); do
    aws logs filter-log-events --log-group-name "$lg" --filter-pattern '"RESIDENCY"' --output json \
      | python3 -c 'import json, sys
for e in json.load(sys.stdin)["events"]:
    print(e["message"].split("RESIDENCY ", 1)[1].strip())' >> "$out.jsonl"
  done
  python3 - "$out.jsonl" "$out.csv" <<'PY'
import csv, json, sys
rows = [json.loads(line) for line in open(sys.argv[1]) if line.strip()]
cols = []
for r in rows:
    cols += [k for k in r if k not in cols]
rows.sort(key=lambda r: (r["fn"], r["ts"], r["invocation"]))
with open(sys.argv[2], "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=cols)
    w.writeheader()
    w.writerows(rows)
print(f"{len(rows)} records -> {sys.argv[2]}")
PY
}

cmd_stop() {
  local s
  for s in $(aws scheduler list-schedules --name-prefix "$PREFIX-" \
               --query 'Schedules[].Name' --output text); do
    aws scheduler delete-schedule --name "$s"
    echo "deleted schedule $s"
  done
}

cmd_teardown() {
  cmd_stop
  local fn
  for fn in $(aws lambda list-functions \
                --query "Functions[?starts_with(FunctionName, '$PREFIX-')].FunctionName" --output text); do
    aws lambda delete-function --function-name "$fn"
    echo "deleted function $fn"
  done
  aws iam detach-role-policy --role-name "$LROLE" --policy-arn "$BASIC" 2>/dev/null || true
  aws iam delete-role --role-name "$LROLE" 2>/dev/null || true
  aws iam delete-role-policy --role-name "$SROLE" --policy-name invoke-probe 2>/dev/null || true
  aws iam delete-role --role-name "$SROLE" 2>/dev/null || true
  aws s3 rb "s3://$BUCKET" --force 2>/dev/null || true
  echo "log groups /aws/lambda/$PREFIX-* are kept so collect still works."
  echo "Delete them in the CloudWatch console once the CSV is safely downloaded."
}

"cmd_$CMD"
