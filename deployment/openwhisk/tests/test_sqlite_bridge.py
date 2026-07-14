"""Canonical SQLite bridge + oracle tests. Uses a tiny synthetic DB so it runs
without the 102 MB canonical DB."""
import os
import sys
import unittest

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "action"))
sys.path.insert(0, HERE)

import _fixture  # noqa: E402

try:
    import sqlite_bridge  # noqa: E402
    _HAVE_BRIDGE = True
except OSError:  # pragma: no cover - libsqlite3 missing
    _HAVE_BRIDGE = False
import oracle  # noqa: E402


@unittest.skipUnless(_HAVE_BRIDGE, "libsqlite3 not available for ctypes bridge")
class TestBridge(unittest.TestCase):
    def setUp(self):
        self.db = _fixture.make_tiny_db(50)

    def tearDown(self):
        os.remove(self.db)

    def test_canonical_select_payload_hit(self):
        w = sqlite_bridge.WarmDb(self.db, cache_size=0, mmap_size=0)
        try:
            hit, payload, us = w.query(7)
            self.assertEqual(hit, 1)
            self.assertEqual(payload, bytes([7]) * 100)   # canonical returns payload
            self.assertGreaterEqual(us, 0.0)
        finally:
            w.close()

    def test_not_found(self):
        w = sqlite_bridge.WarmDb(self.db)
        try:
            hit, payload, _ = w.query(9999)
            self.assertEqual((hit, payload), (0, None))
            self.assertEqual(oracle.digest_payload(hit, payload), (0, "NOTFOUND"))
        finally:
            w.close()

    def test_digest_matches_oracle(self):
        w = sqlite_bridge.WarmDb(self.db)
        try:
            hit, payload, _ = w.query(7)
            h, dig = oracle.digest_payload(hit, payload)
            import hashlib
            self.assertEqual(dig, hashlib.sha256(bytes([7]) * 100).hexdigest())
        finally:
            w.close()

    def test_statement_reuse_across_queries(self):
        # one prepared statement reused; different keys give different payloads
        w = sqlite_bridge.WarmDb(self.db)
        try:
            _, p1, _ = w.query(1)
            _, p2, _ = w.query(2)
            self.assertNotEqual(p1, p2)
        finally:
            w.close()

    def test_pager_cache_not_serving(self):
        # with cache_size=0, repeated identical queries still miss (not served by
        # the SQLite pager cache) -- proving the OS page cache is the data cache.
        w = sqlite_bridge.WarmDb(self.db, cache_size=0, mmap_size=0)
        try:
            w.cache_hit_miss(reset=True)
            for _ in range(5):
                w.query(7)
            hit, miss = w.cache_hit_miss(reset=True)
            self.assertGreater(miss, 0)
        finally:
            w.close()


if __name__ == "__main__":
    unittest.main()
