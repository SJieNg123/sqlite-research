"""Build the deterministic OpenWhisk action-code zip deployed with `--main main`.

Observed OpenWhisk fact this encodes: a custom Docker image alone is not enough --
the action must also carry the Python source as a zip, or the runtime reports
"Missing main/no code to execute". The Docker image provides the runtime + the
baked measurement artifacts; this archive provides ONLY the action code.

Layout is FLAT (the layout that deployed cleanly on WS2):
  * action/main.py  ->  __main__.py   (the module OpenWhisk imports; `--main main`
    selects its main() function)
  * action/session.py, residency.py, sqlite_bridge.py, oracle.py  ->  archive root
    (the siblings main.py imports under the OpenWhisk flat-layout ImportError path)

Deterministic: fixed member order + fixed zip timestamp, so identical sources
always yield a byte-identical archive (reproducible deploys). The archive is
machine-local build output (written under _runs/, git-ignored); it is never
committed.
"""
import os
import sys
import zipfile

# main.py is the entrypoint module; it is shipped AS __main__.py (deployed with
# `--main main`, so OpenWhisk calls __main__.main()).
ENTRY_SOURCE = "main.py"
ENTRY_ARCNAME = "__main__.py"
# sibling modules main.py imports under the OpenWhisk flat layout.
MODULE_SOURCES = ("session.py", "residency.py", "sqlite_bridge.py", "oracle.py")
# The exact, complete set of archive members (nothing else may be added).
EXPECTED_MEMBERS = tuple(sorted((ENTRY_ARCNAME,) + MODULE_SOURCES))
# Fixed zip epoch (1980-01-01); zip cannot represent earlier. Deterministic.
_FIXED_MTIME = (1980, 1, 1, 0, 0, 0)


def build(action_dir, out_path):
    """Write the deterministic action zip to out_path from the sources in
    action_dir. Returns the archive member names in stable order."""
    members = [(ENTRY_SOURCE, ENTRY_ARCNAME)] + [(m, m) for m in MODULE_SOURCES]
    members.sort(key=lambda t: t[1])  # stable member order (by archive name)
    with zipfile.ZipFile(out_path, "w") as z:
        for src, arc in members:
            with open(os.path.join(action_dir, src), "rb") as f:
                data = f.read()
            zi = zipfile.ZipInfo(arc, date_time=_FIXED_MTIME)
            zi.external_attr = 0o644 << 16
            zi.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(zi, data)
    return [arc for _, arc in members]


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("usage: make_action_zip.py <action_dir> <out.zip>")
    names = build(sys.argv[1], sys.argv[2])
    print("\n".join(names))
