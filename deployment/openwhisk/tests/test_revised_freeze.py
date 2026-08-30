"""REVISED OpenWhisk-vs-workstation effectiveness freeze: regression + guard (§14/§12).

The one-time, pre-registered revision supersedes EXACTLY seven of the 55 first-query
cells with their targeted, independently rebuilt, exactly position-balanced replication
estimates (five from the sixth campaign portability_outlier_replication, two from the
seventh portability_ych01_followup). Precedence seventh > sixth > historical, per cell.

These tests encode WHY the revision is trustworthy, not merely WHAT numbers it holds:

  * the historical table is preserved byte-identically and is NOT the paper-facing input;
  * nothing beyond the seven declared cells moved (the other 48 are byte-carried);
  * per-cell precedence + provenance is exactly the audited campaign, not a rounded guess;
  * the recomputed global statistics come from the revised freeze, from scratch;
  * the single OpenWhisk-negative cell is workstation-neutral (not a strong-WS failure);
  * the revised freeze is the FINAL freeze: the builder is deterministic/idempotent, and
    no paper-facing consumer reads the historical table any more (they read the revised).

Position effects are described only as pair-position / short-lived execution-state /
execution-storage-state dependence -- never attributed to page-cache carryover.
"""
import csv
import hashlib
import importlib
import json
import os
import statistics as st
import sys
import unittest

HERE = os.path.dirname(__file__)
ANALYSIS = os.path.join(HERE, "..", "analysis")
sys.path.insert(0, ANALYSIS)
sys.path.insert(0, HERE)
import _fixture  # noqa: E402

REPO = _fixture.REPO
CMP = os.path.join(REPO, "deployment/openwhisk/analysis/comparison")

CANONICAL = os.path.join(CMP, "effectiveness_ow_vs_workstation.csv")
HIST_FREEZE = os.path.join(CMP, "effectiveness_ow_vs_workstation_historical_freeze.csv")
REVISED = os.path.join(CMP, "effectiveness_ow_vs_workstation_revised_freeze.csv")
MANIFEST = os.path.join(CMP, "effectiveness_freeze_revision.json")
STATS = os.path.join(CMP, "effectiveness_revised_stats.json")

HISTORICAL_SHA256 = "d7cc7673068b975603ac2b78409f1518ac3d4740d2f78e417df01874f235803a"
REVISED_SHA256 = "072e294ef2fde500983dba63ef01d283acaf286c5c81cdd8d47dbaddcf921eb7"

# The seven superseded cells and their authoritative campaign (precedence encoded).
SIXTH = "portability_outlier_replication"
SEVENTH = "portability_ych01_followup"
SUPERSEDE = {
    ("C", "layers_92"): SIXTH,
    ("C", "2d"): SIXTH,
    ("C_hit", "2e_K40"): SIXTH,
    ("C", "layers_5"): SIXTH,
    ("YCu", "layers_5"): SIXTH,
    ("YCh01", "layers_5"): SEVENTH,
    ("YCh01", "2f_top14"): SEVENTH,
}
POSITION_SENSITIVE = {  # exactly these four carry the descriptive-aggregate flag
    ("C", "layers_92"), ("C", "2d"), ("YCu", "layers_5"), ("YCh01", "2f_top14"),
}
HISTORICAL_COLS = ["workload", "strategy", "R_ws", "n_ws", "ws_agg", "R_ow",
                   "n_ow_pairs", "n_ow_seeds", "ow_pos", "cat_ws", "cat_ow",
                   "sign_agree", "abs_diff", "low_conf"]
NEUTRAL_BAND = 0.10
STRONG_WS = 0.30


def _sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _rows(path):
    with open(path) as f:
        return list(csv.DictReader(f))


def _key(r):
    return (r["workload"], r["strategy"])


def _as_bool(s):
    return str(s).strip().lower() == "true"


class RevisedFreeze(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.hist = _rows(HIST_FREEZE)
        cls.rev = _rows(REVISED)
        cls.manifest = json.load(open(MANIFEST))
        cls.stats = json.load(open(STATS))

    # ---- historical preservation -------------------------------------------------
    def test_historical_preserved_byte_identical(self):
        # The historical table is preserved byte-identically (a byte-copy of the
        # unchanged canonical table). Nothing is deleted or mutated.
        self.assertEqual(_sha(HIST_FREEZE), HISTORICAL_SHA256)
        self.assertEqual(_sha(CANONICAL), HISTORICAL_SHA256,
                         "canonical historical table must stay byte-unchanged")
        self.assertEqual(self.manifest["historical_source_sha256"], HISTORICAL_SHA256)
        self.assertEqual(len(self.hist), 55)

    # ---- revised existence + sha -------------------------------------------------
    def test_revised_freeze_exists_and_sha_matches_manifest(self):
        self.assertTrue(os.path.exists(REVISED))
        self.assertEqual(_sha(REVISED), REVISED_SHA256)
        self.assertEqual(self.manifest["revised_freeze_sha256"], REVISED_SHA256)
        self.assertNotEqual(_sha(REVISED), HISTORICAL_SHA256,
                            "revised freeze must differ from the historical table")

    # ---- exactly seven changed, no eighth ---------------------------------------
    def test_exactly_seven_superseded_no_eighth(self):
        hist = {_key(r): r for r in self.hist}
        rev = {_key(r): r for r in self.rev}
        self.assertEqual(set(hist), set(rev), "cell set must be identical")
        changed = set()
        for k in hist:
            if any(hist[k][c] != rev[k][c] for c in HISTORICAL_COLS):
                changed.add(k)
        self.assertEqual(changed, set(SUPERSEDE),
                         "exactly the 7 declared cells may differ on historical columns")
        self.assertEqual(len(self.manifest["superseded_cells"]), 7)
        self.assertEqual(self.manifest["unchanged_cell_count"], 48)

    def test_unchanged_cells_byte_carry_historical_columns(self):
        hist = {_key(r): r for r in self.hist}
        for r in self.rev:
            if _key(r) in SUPERSEDE:
                continue
            for c in HISTORICAL_COLS:
                self.assertEqual(r[c], hist[_key(r)][c],
                                 f"unchanged cell {_key(r)} col {c} drifted")
            self.assertEqual(r["evidence_campaign"], "historical")
            self.assertFalse(_as_bool(r["position_sensitive"]))

    # ---- per-cell precedence + provenance ---------------------------------------
    def test_precedence_and_provenance_each_cell(self):
        by_cell = {(s["workload"], s["strategy"]): s
                   for s in self.manifest["superseded_cells"]}
        self.assertEqual(set(by_cell), set(SUPERSEDE))
        # the two cells a later campaign targeted resolve to the SEVENTH campaign
        self.assertEqual(by_cell[("YCh01", "layers_5")]["evidence_campaign"], SEVENTH)
        self.assertEqual(by_cell[("YCh01", "2f_top14")]["evidence_campaign"], SEVENTH)
        self.assertIn("seventh > sixth > historical",
                      by_cell[("YCh01", "layers_5")]["precedence"])
        # C_hit/2e_K40 stays with the SIXTH campaign
        self.assertEqual(by_cell[("C_hit", "2e_K40")]["evidence_campaign"], SIXTH)
        for cell, campaign in SUPERSEDE.items():
            s = by_cell[cell]
            self.assertEqual(s["evidence_campaign"], campaign)
            self.assertTrue(s["execution_git_sha"])
            self.assertEqual(len(s["run_config_sha256"]), 64)
            # exactly position-balanced (X/X) with the recorded pair count
            a, b = s["exact_position_balance"].split("/")
            self.assertEqual(a, b, f"{cell} not exactly balanced")
            self.assertEqual(int(a) + int(b), s["pair_count"])
            self.assertTrue(s["provenance_normalized_pairs"])

    # ---- coverage / lp separation -----------------------------------------------
    def test_exactly_55_non_lp_cells_and_lp_excluded(self):
        self.assertEqual(len(self.rev), 55)
        self.assertFalse(any(r["strategy"].startswith("lp") for r in self.rev),
                         "libprefetch cells are compared separately, not in this table")
        self.assertEqual(self.manifest["coverage"], "65/65")
        self.assertEqual(self.stats["coverage"], "65/65")

    # ---- position-sensitive flags -----------------------------------------------
    def test_position_sensitive_exactly_four(self):
        flagged = {_key(r) for r in self.rev if _as_bool(r["position_sensitive"])}
        self.assertEqual(flagged, POSITION_SENSITIVE)
        self.assertEqual(self.stats["n_position_sensitive"], 4)

    # ---- global metrics recomputed from scratch ---------------------------------
    def test_global_metrics_recompute_from_revised(self):
        # independent recomputation (does NOT trust the emitted stats JSON)
        strong = [r for r in self.rev if float(r["R_ws"]) >= STRONG_WS]
        strong_eff = [r for r in strong if float(r["R_ow"]) >= NEUTRAL_BAND]
        self.assertEqual(len(strong), 41)
        self.assertEqual(len(strong_eff), 41,
                         "every strongly workstation-effective cell must be effective on OW")
        direction = sum(1 for r in self.rev if _as_bool(r["sign_agree"]))
        self.assertEqual(direction, 46)
        pos_sens = sum(1 for r in self.rev if _as_bool(r["position_sensitive"]))
        self.assertEqual(pos_sens, 4)
        # the emitted stats file must agree with the from-scratch recomputation
        self.assertEqual(self.stats["strong_ws_agreement"], "41/41")
        self.assertEqual(self.stats["direction_agreement_all"], "46/55")
        self.assertEqual(round(self.stats["rho_all"], 2), 0.76)
        self.assertEqual(round(self.stats["rho_high_confidence"], 2), 0.79)
        self.assertEqual(round(self.stats["rho_high_conf_clean"], 2), 0.81)
        self.assertEqual(self.stats["source"],
                         "effectiveness_ow_vs_workstation_revised_freeze.csv")

    def test_only_ow_negative_cell_is_workstation_neutral(self):
        harmful = [r for r in self.rev if r["cat_ow"] == "harmful"]
        self.assertEqual(len(harmful), 1, "revised freeze has exactly one OW-negative cell")
        h = harmful[0]
        self.assertEqual(_key(h), ("YCh01", "layers_5"))
        self.assertEqual(h["cat_ws"], "neutral",
                         "the sole OW-negative cell is workstation-NEUTRAL, not a strong-WS "
                         "strategy that failed")
        self.assertLess(float(h["R_ow"]), -0.10)

    # ---- manifest fields / accounting -------------------------------------------
    def test_manifest_accounting_and_final_policy(self):
        m = self.manifest
        self.assertEqual(m["total_cells"], 55)
        self.assertEqual(m["superseded_cell_count"], 7)
        self.assertEqual(m["unchanged_cell_count"], 48)
        self.assertFalse(m["pooled"])
        self.assertFalse(self.stats["pooled"])
        self.assertIn("FINAL", m["policy"])
        self.assertIn("page-cache carryover", m["position_sensitive_semantics"])
        self.assertIn("NOT attributed", m["position_sensitive_semantics"])
        self.assertEqual(len(m["campaigns"]), 7,
                         "seven immutable campaigns; never pooled into one estimator")

    # ---- paper-facing consumers read the revised freeze, not the historical -----
    def test_paper_facing_consumers_use_revised(self):
        def _read(rel):
            with open(os.path.join(REPO, rel)) as f:
                return f.read()
        src = _read("figures/19c_openwhisk_effectiveness_bars.py")
        self.assertIn("effectiveness_ow_vs_workstation_revised_freeze.csv", src)
        self.assertNotIn('CSV = ROOT / "deployment/openwhisk/analysis/comparison/'
                         'effectiveness_ow_vs_workstation.csv"', src)
        # the historical dependency is explicitly the *historical* freeze, never revised
        ych = _read("deployment/openwhisk/analysis/build_ych01_followup_outputs.py")
        self.assertIn("effectiveness_ow_vs_workstation_historical_freeze.csv", ych)
        # the canonical writer must not clobber the revised freeze path
        cmp_src = _read("deployment/openwhisk/analysis/compare_effectiveness.py")
        self.assertNotIn("revised_freeze", cmp_src,
                         "the historical-comparison writer must never target the revised freeze")

    # ---- §12 guard: deterministic + not overwritable-in-place-with-other-bytes ---
    def test_builder_is_idempotent_guard(self):
        before_rev = open(REVISED, "rb").read()
        before_hist = open(HIST_FREEZE, "rb").read()
        before_manifest = open(MANIFEST, "rb").read()
        mod = importlib.import_module("build_revised_freeze")
        importlib.reload(mod)
        mod.build()  # re-run must reproduce byte-identical outputs (fail-closed if not)
        self.assertEqual(open(REVISED, "rb").read(), before_rev,
                         "re-running the builder must not change the revised freeze bytes")
        self.assertEqual(_sha(REVISED), REVISED_SHA256)
        self.assertEqual(open(HIST_FREEZE, "rb").read(), before_hist)
        # manifest is stable except for nothing (fully deterministic)
        self.assertEqual(open(MANIFEST, "rb").read(), before_manifest)


if __name__ == "__main__":
    unittest.main()
