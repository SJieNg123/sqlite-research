"""Schedule determinism, one-to-one pairing, and per-seed-then-cross-seed
aggregation with strict no-mix rules."""
import csv
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "client"))
import build_schedule  # noqa: E402
import summarize  # noqa: E402
import collect  # noqa: E402

IDS = {"run_config_sha256": "a" * 64, "artifact_manifest_sha256": "b" * 64,
       "action_image_digest": "sha256:img"}

BASE_ROW = dict(run_config_sha256="a" * 64, artifact_manifest_sha256="b" * 64,
                action_image_digest="sha256:img", first_operation_id="0", valid="True")


def write_summary(tmp, rows):
    cols = sorted({k for r in rows for k in r} | {"valid"})
    with open(os.path.join(tmp, "summary.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow(r)


def arm(pair_id, strategy, seed, session="S1", hm="warm", wl="A", fq=None, deliver=0.0):
    d = dict(BASE_ROW, pair_id=pair_id, strategy=strategy, seed=str(seed),
             warm_session_id=session, handle_mode=hm, workload=wl,
             first_query_us=str(fq if fq is not None else (500 if strategy == "baseline" else 360)),
             deliver_us=str(deliver), open_us="0")
    return d


class TestSchedule(unittest.TestCase):
    def test_ten_reps_ten_pairs(self):
        s = build_schedule.build_schedule(["A"], [1], [0], ["warm"], ["2d"], 10, 7, IDS)
        self.assertEqual(s["counts"]["pairs"], 10)
        self.assertEqual(s["counts"]["invocations"], 20)
        for p in s["pairs"]:
            self.assertEqual(sorted(p["order"]), ["2d", "baseline"])

    def test_ab_ba_deterministic(self):
        a = build_schedule.build_schedule(["A"], [1, 2], [0], ["warm"], ["2d"], 3, 99, IDS)
        b = build_schedule.build_schedule(["A"], [1, 2], [0], ["warm"], ["2d"], 3, 99, IDS)
        self.assertEqual([p["order"] for p in a["pairs"]],
                         [p["order"] for p in b["pairs"]])

    def test_warmup_is_diagnostic(self):
        s = build_schedule.build_schedule(["A"], [1], [0], ["warm"], ["2d"], 1, 1, IDS)
        self.assertTrue(s["warmup"]["diagnostic_mode"])


class TestPairing(unittest.TestCase):
    def _summarize(self, rows, metric="first_query_us"):
        tmp = tempfile.mkdtemp()
        write_summary(tmp, rows)
        try:
            return summarize.summarize(tmp, metric)
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def test_one_to_one_valid(self):
        rows = [arm("p1", "baseline", 1), arm("p1", "2d", 1)]
        r = self._summarize(rows)
        self.assertEqual(r["n_valid_pairs"], 1)

    def test_duplicate_baseline_fails(self):
        rows = [arm("p1", "baseline", 1), arm("p1", "baseline", 1), arm("p1", "2d", 1)]
        r = self._summarize(rows)
        self.assertEqual(r["duplicate_pairs"], 1)
        self.assertEqual(r["n_valid_pairs"], 0)

    def test_missing_arm_fails(self):
        rows = [arm("p1", "baseline", 1)]
        r = self._summarize(rows)
        self.assertEqual(r["incomplete_pairs"], 1)

    def test_session_break_invalidates_pair(self):
        rows = [arm("p1", "baseline", 1, session="S1"),
                arm("p1", "2d", 1, session="S2")]
        r = self._summarize(rows)
        self.assertEqual(r["session_break_pairs"], 1)
        self.assertEqual(r["n_valid_pairs"], 0)

    def test_per_seed_then_cross_seed(self):
        rows = [arm("p1", "baseline", 1), arm("p1", "2d", 1),
                arm("p2", "baseline", 2), arm("p2", "2d", 2)]
        r = self._summarize(rows)
        agg = list(r["aggregate"].values())[0]
        self.assertEqual(agg["n_seeds"], 2)
        self.assertEqual(agg["cross_seed_equal_weight_mean_pct"], -28.0)

    def test_unequal_reps_do_not_reweight_seeds(self):
        # seed 1: three reps all -28%; seed 2: one rep at -10%. Equal-weight
        # cross-seed mean = mean(-28, -10) = -19, NOT weighted by rep count.
        rows = []
        for rep in range(3):
            rows += [arm("p1_%d" % rep, "baseline", 1, fq=500),
                     arm("p1_%d" % rep, "2d", 1, fq=360)]
        rows += [arm("p2", "baseline", 2, fq=500), arm("p2", "2d", 2, fq=450)]  # -10%
        r = self._summarize(rows)
        agg = list(r["aggregate"].values())[0]
        self.assertEqual(agg["per_seed_mean_pct"]["1"], -28.0)
        self.assertEqual(agg["per_seed_mean_pct"]["2"], -10.0)
        self.assertEqual(agg["cross_seed_equal_weight_mean_pct"], -19.0)

    def test_workloads_do_not_aggregate_together(self):
        rows = [arm("pA", "baseline", 1, wl="A"), arm("pA", "2d", 1, wl="A"),
                arm("pB", "baseline", 1, wl="B"), arm("pB", "2d", 1, wl="B")]
        r = self._summarize(rows)
        self.assertEqual(len(r["aggregate"]), 2)   # A and B are separate groups

    def test_warm_and_standalone_do_not_aggregate(self):
        rows = [arm("pw", "baseline", 1, hm="warm"), arm("pw", "2d", 1, hm="warm"),
                arm("ps", "baseline", 1, hm="standalone"), arm("ps", "2d", 1, hm="standalone")]
        r = self._summarize(rows, metric="first_query_us")
        self.assertEqual(len(r["aggregate"]), 2)   # warm and standalone separate

    def test_e2e_warm_only_for_warm_mode(self):
        rows = [arm("ps", "baseline", 1, hm="standalone"),
                arm("ps", "2d", 1, hm="standalone")]
        r = self._summarize(rows, metric="e2e_warm_us")
        # standalone rows yield no e2e_warm metric -> no paired effects
        self.assertEqual(r["n_paired_effects"], 0)


if __name__ == "__main__":
    unittest.main()
