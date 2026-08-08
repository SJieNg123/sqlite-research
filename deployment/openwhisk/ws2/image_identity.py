#!/usr/bin/env python3
"""Registry image-identity helpers for the WS2 build/deploy lifecycle.

Single source of truth for the identity rules the shell stages enforce, so the
rules are unit-tested behaviourally instead of being duplicated (and drifting) in
shell. Each rule below fixes a bug found during the first real OpenWhisk deploy:

  * untagged_repo(repo)
        repository with any trailing :tag stripped from the FINAL path component
        (a host:port earlier in the reference keeps its colon).
  * select_repo_digest(image_repo, repo_digests)
        pick the ONE RepoDigest whose repository EXACTLY equals image_repo; raise
        if zero or more than one qualifies. docker lists several RepoDigests -- a
        registry-less `name@sha256:` alias AND the host-qualified
        `host:port/name@sha256:` we pushed -- and taking the first entry dropped
        the registry host, mis-pinning the bound image.
  * same_repository(exec_ref, digest)
        the execution tag <repo>:<sha> OpenWhisk runs and the bound
        <repo>@sha256:... must name the SAME repository.
  * is_pinned_base_reference(value)
        a COMPLETE pinned base ref <repo>@sha256:<64hex>; a bare `@sha256:...`
        (empty repository) or a mutable tag is refused (the Dockerfile does
        `FROM ${BASE_RUNTIME}`).

CLI (used by 01_build_image.sh / 02_deploy.sh); exit 0 on success/true, 1 on
failure/false, 2 on a usage error:

  image_identity.py exec-ref <repo> <git_sha>      -> prints <untagged-repo>:<git_sha>
  image_identity.py select-digest <repo> <json>    -> prints the single matching digest
  image_identity.py same-repo <exec_ref> <digest>  -> exit 0 iff same repository
  image_identity.py check-base <value>             -> exit 0 iff a pinned base reference
"""
import json
import re
import sys

_SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}$")


def untagged_repo(repo):
    """Strip a trailing :tag from the final path component only (an earlier
    host:port keeps its colon)."""
    last = repo.rsplit("/", 1)[-1]
    if ":" in last:
        repo = repo[: repo.rfind(":")]
    return repo


def _split_digest(ref):
    """(repository, 'sha256:...') for a repo@sha256:... reference, else (None, None)."""
    if "@" not in ref:
        return None, None
    repo, _, sha = ref.partition("@")
    return repo, sha


def select_repo_digest(image_repo, repo_digests):
    """Return the single RepoDigest whose repository EXACTLY equals image_repo
    (after untagging). Raise ValueError unless exactly one qualifies.

    Never returns docker's first entry blindly: the list mixes a registry-less
    alias (name@sha256:...) with the host-qualified digest we pushed, and only the
    host-qualified one is a valid pull/pin reference."""
    repo = untagged_repo(image_repo)
    matches = sorted(
        {
            d
            for d in (repo_digests or [])
            if isinstance(d, str)
            for r, sha in [_split_digest(d)]
            if r == repo and sha and _SHA256_RE.match(sha)
        }
    )
    if len(matches) == 1:
        return matches[0]
    raise ValueError(
        "expected exactly one RepoDigest for repository %r, found %d: %r"
        % (repo, len(matches), matches)
    )


def same_repository(exec_ref, digest):
    """True iff the execution tag and the bound digest name the same repository."""
    dig_repo, sha = _split_digest(digest)
    if dig_repo is None or not (sha and _SHA256_RE.match(sha)):
        return False
    return untagged_repo(exec_ref) == dig_repo


def is_pinned_base_reference(value):
    """True iff value is a COMPLETE pinned reference <repo>@sha256:<64hex> with a
    non-empty repository. A bare '@sha256:...' or a mutable tag is not."""
    repo, sha = _split_digest(value or "")
    return bool(repo) and bool(sha) and _SHA256_RE.match(sha) is not None


def _main(argv):
    if len(argv) < 2:
        sys.stderr.write(
            "usage: image_identity.py <exec-ref|select-digest|same-repo|check-base> ...\n")
        return 2
    cmd = argv[1]
    try:
        if cmd == "exec-ref":
            print("%s:%s" % (untagged_repo(argv[2]), argv[3]))
            return 0
        if cmd == "select-digest":
            raw = argv[3]
            digs = json.loads(raw) if raw.strip() else []
            print(select_repo_digest(argv[2], digs))
            return 0
        if cmd == "same-repo":
            return 0 if same_repository(argv[2], argv[3]) else 1
        if cmd == "check-base":
            return 0 if is_pinned_base_reference(argv[2]) else 1
    except (IndexError, ValueError) as e:
        sys.stderr.write("%s\n" % e)
        return 1
    sys.stderr.write("unknown subcommand: %s\n" % cmd)
    return 2


if __name__ == "__main__":
    sys.exit(_main(sys.argv))
