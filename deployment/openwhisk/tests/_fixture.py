"""Shared test fixtures. A tiny synthetic SQLite DB lets the bridge/oracle tests
run without the 102 MB canonical DB; tests that specifically need the canonical
artifacts skip cleanly when they are absent."""
import os
import sqlite3
import tempfile

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
CANONICAL_DB = os.path.join(REPO, "pipeline/preparation/layout_rewriter/runs/test.db")
EXAMPLE_MANIFEST = os.path.join(REPO, "deployment/openwhisk/config/artifacts.example.json")


def make_tiny_db(n=50):
    """Create a tiny items(id,k1,k2,payload) DB matching the canonical schema and
    the canonical query. Returns the path (caller removes it)."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, k1 TEXT NOT NULL, "
                 "k2 TEXT NOT NULL, payload BLOB NOT NULL)")
    conn.executemany("INSERT INTO items VALUES (?,?,?,?)",
                     [(i, "k1_%d" % i, "k2_%d" % i, bytes([i % 256]) * 100)
                      for i in range(1, n + 1)])
    conn.commit()
    conn.close()
    return path


def have_canonical():
    return os.path.exists(CANONICAL_DB) and os.path.exists(EXAMPLE_MANIFEST)
