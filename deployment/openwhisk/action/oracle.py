"""Single source of truth for the first-query result oracle.

Both the action (`main.py`) and the manifest generator
(`build_artifact_manifest.py`) import this module so the expected/observed
result digest is computed by identical code. The digest is a stable, order-fixed
hash of the returned row; a not-found lookup has its own sentinel. This lets the
correctness oracle assert the *exact* expected hit/not-found and digest per
first operation rather than hard-coding ``query_hit == 1``.
"""
import hashlib

READ_SQL = "SELECT id,k1,k2,payload FROM items WHERE id=?"
FIELD_SEP = b"\x1f"
NOTFOUND = "NOTFOUND"


def digest_row(row):
    """Return (hit, digest). row is a tuple of columns or None.
    hit == 1 and a sha256 hex digest for a found row; hit == 0 and the NOTFOUND
    sentinel otherwise."""
    if row is None:
        return 0, NOTFOUND
    h = hashlib.sha256()
    for col in row:
        h.update(col if isinstance(col, (bytes, bytearray)) else str(col).encode())
        h.update(FIELD_SEP)
    return 1, h.hexdigest()


def run_read(conn, key):
    """Execute the canonical read against an open connection and return the row.
    Statement reuse is handled by sqlite3's internal statement cache; the SQL
    text is constant so the compiled statement is reused across invocations."""
    return conn.execute(READ_SQL, (key,)).fetchone()
