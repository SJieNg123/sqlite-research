#!/usr/bin/env python3
"""Overwrite the six outlier cells in the frozen 55-cell effectiveness comparison
table with their INDEPENDENT REPLICATION values (campaign portability_outlier_replication,
evidence b684df8860b1), run under EXACT within-pair position balance.

Why this exists / provenance note
----------------------------------
The original R_ow for these six cells came from the primary/portability campaigns where
the cell was single-instance (n<=3 pairs) or position-imbalanced -- flagged low_conf and,
for three of them, a sign flip vs the workstation. The replication re-ran each cell under
exact position balance (5 static cells at 10 baseline-first / 10 target-first = 20 pairs;
C_hit/2e_K40 keyed at 3 seeds x (3,3) = 18 pairs). Those balanced medians are better-powered
and supersede the confounded originals; per author decision (2026-08-29) the comparison
table is overwritten in place with them (all six cells, honest values incl. the one that
now reads negative). Original values are preserved in the replication analysis tree
(analysis/outlier_replication/) and in analysis/comparison/outlier_replication_report.csv.

Derived columns are recomputed with the SAME rules as compare_effectiveness.py:
  cat = category(R) (NEUTRAL_BAND=0.10); sign_agree = cat_ws==cat_ow; abs_diff=|R_ow-R_ws|;
  low_conf = (n<=3) or (imbalance==n)  -> now False for all six (n>=18, imbalance==0).
R_ws / n_ws / ws_agg / cat_ws are unchanged (workstation side untouched).
"""
import csv
import pathlib

NEUTRAL_BAND = 0.10  # identical to compare_effectiveness.py
CSV = pathlib.Path(__file__).resolve().parent / "comparison" / "effectiveness_ow_vs_workstation.csv"


def category(R):
    if R >= NEUTRAL_BAND:
        return "effective"
    if R <= -NEUTRAL_BAND:
        return "harmful"
    return "neutral"


# (workload, strategy) -> replicated R_ow, total pairs, seeds, (tgt_first, base_first)
# Source: analysis/outlier_replication/replication_cell_comparison.csv (balanced medians).
REPL = {
    ("YCu",   "layers_5"):  (0.2900, 20, 1, (10, 10)),
    ("YCh01", "layers_5"):  (-0.2425, 20, 1, (10, 10)),
    ("C",     "2d"):        (0.4316, 20, 1, (10, 10)),
    ("C",     "layers_5"):  (0.4185, 20, 1, (10, 10)),
    ("C",     "layers_92"): (0.3832, 20, 1, (10, 10)),
    ("C_hit", "2e_K40"):    (0.4865, 18, 3, (9, 9)),
}


def main():
    rows = list(csv.DictReader(open(CSV)))
    assert len(rows) == 55, f"expected 55 cells, got {len(rows)}"
    fields = list(rows[0].keys())

    patched = 0
    for r in rows:
        key = (r["workload"], r["strategy"])
        if key not in REPL:
            continue
        R_ow, n_pairs, n_seeds, (tgt_first, base_first) = REPL[key]
        R_ws = float(r["R_ws"])
        imbalance = abs(tgt_first - base_first)
        r["R_ow"] = f"{R_ow:.4f}"
        r["n_ow_pairs"] = str(n_pairs)
        r["n_ow_seeds"] = str(n_seeds)
        r["ow_pos"] = f"{tgt_first}/{base_first}"
        r["cat_ow"] = category(R_ow)
        r["sign_agree"] = str(category(R_ws) == category(R_ow))
        r["abs_diff"] = f"{abs(R_ow - R_ws):.4f}"
        r["low_conf"] = str((n_pairs <= 3) or (imbalance == n_pairs))
        patched += 1

    assert patched == 6, f"expected to patch 6 cells, patched {patched}"

    with open(CSV, "w", newline="") as f:
        wtr = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        wtr.writeheader()
        wtr.writerows(rows)

    print(f"patched {patched} cells in {CSV.name}; total rows still {len(rows)}")


if __name__ == "__main__":
    main()
