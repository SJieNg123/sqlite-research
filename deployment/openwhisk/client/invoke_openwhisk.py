#!/usr/bin/env python3
"""Real OpenWhisk invocation adapter (NOT executed in Phase 5A.2).

Provides `invoke_fn` / `activation_fn` factories for `collect.collect(...)` that
drive a deployed action via the `wsk` CLI (blocking, result+full activation) and
preserve the platform metadata the atomic protocol requires:

  - activation id, activation status/success, duration, initTime (cold/warm)
  - the action response `request_id`
  - client elapsed time (measured by the collector)
  - `wsk` stderr and exit code

Phase 5A.2 does not deploy or invoke anything; importing this module is safe, but
`main()` and `run_batch()` refuse to execute so no accidental invocation occurs.
Enable execution only in the measurement phase by passing `allow_execute=True`.
"""
import argparse
import json
import subprocess
import time


def make_invoke_fn(action_name, wsk="wsk", extra_args=None, timeout=120,
                   allow_execute=False):
    """Return invoke_fn(request)->response_dict. Blocking `wsk action invoke -r`
    returns the action's result JSON (the handler response)."""
    extra_args = extra_args or []

    def invoke_fn(request):
        if not allow_execute:
            raise RuntimeError("invoke_openwhisk disabled in this phase "
                               "(pass allow_execute=True in the measurement phase)")
        cmd = [wsk, "action", "invoke", action_name, "-r", "-b"] + extra_args
        for k, v in request.items():
            cmd += ["-p", k, json.dumps(v) if not isinstance(v, str) else v]
        t0 = time.monotonic_ns()
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        elapsed_us = (time.monotonic_ns() - t0) / 1000.0
        try:
            resp = json.loads(proc.stdout) if proc.stdout.strip() else {}
        except json.JSONDecodeError:
            resp = {"error": "unparseable wsk stdout", "error_stage": "platform"}
        resp.setdefault("_wsk", {})
        resp["_wsk"].update({"exit_code": proc.returncode,
                             "stderr": proc.stderr[-2000:],
                             "client_elapsed_us": elapsed_us})
        if proc.returncode != 0:
            resp.setdefault("error", "wsk exit %d" % proc.returncode)
            resp.setdefault("error_stage", "platform")
        return resp

    return invoke_fn


def make_activation_fn(wsk="wsk", timeout=60, allow_execute=False):
    """Return activation_fn(request, response)->activation_metadata. Fetches the
    most recent activation record and extracts id/status/duration/initTime."""
    def activation_fn(request, response):
        if not allow_execute:
            return None
        cmd = [wsk, "activation", "list", "--limit", "1", "--json"]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            arr = json.loads(proc.stdout) if proc.stdout.strip() else []
            act = arr[0] if arr else {}
        except (subprocess.SubprocessError, json.JSONDecodeError, IndexError) as e:
            return {"error": "activation_fetch:%s" % e}
        annos = {a.get("key"): a.get("value") for a in act.get("annotations", [])}
        return {"activationId": act.get("activationId"),
                "success": (act.get("response") or {}).get("success"),
                "statusCode": (act.get("response") or {}).get("statusCode"),
                "duration": act.get("duration"),
                "initTime": annos.get("initTime"),
                "waitTime": annos.get("waitTime")}
    return activation_fn


def run_batch(*_a, **_k):  # pragma: no cover
    raise SystemExit("Phase 5A.2: OpenWhisk invocation is out of scope. Use the "
                     "measurement-phase driver with allow_execute=True.")


def main():  # pragma: no cover
    argparse.ArgumentParser(
        description="OpenWhisk invocation adapter (disabled in 5A.2).").parse_args()
    run_batch()


if __name__ == "__main__":
    main()
