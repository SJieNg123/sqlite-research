"""Single source of truth for the first-query result oracle.

The canonical query (matching ``benchmark_harness.c``) is
``SELECT payload FROM items WHERE id=?1`` and the returned value is the payload
blob. The oracle digest is ``sha256(payload)``; a not-found lookup has its own
sentinel. Both the action (via the ctypes ``sqlite_bridge``) and the manifest
generator (via Python ``sqlite3``) import this so the expected/observed digest is
computed by identical code, and correctness is the exact expected hit/not-found +
digest, never a hard-coded ``query_hit == 1``.
"""
import hashlib

# Canonical statement text (payload only), mirroring the C harness.
SELECT_SQL = "SELECT payload FROM items WHERE id=?1"
NOTFOUND = "NOTFOUND"


def digest_payload(hit, payload):
    """Return (hit, digest) from a (hit, payload_bytes|None) pair."""
    if not hit or payload is None:
        return 0, NOTFOUND
    if isinstance(payload, str):
        payload = payload.encode()
    return 1, hashlib.sha256(payload).hexdigest()


def run_read_payload(conn, key):
    """Offline helper (manifest generator) using Python sqlite3: return
    (hit, payload_bytes|None) for the canonical query."""
    row = conn.execute("SELECT payload FROM items WHERE id=?", (key,)).fetchone()
    if row is None:
        return 0, None
    return 1, row[0]
