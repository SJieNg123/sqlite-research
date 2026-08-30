#!/usr/bin/env python3
"""Recompute ALL global effectiveness-portability statistics FROM the revised freeze.

Everything here is derived mechanically from
``effectiveness_ow_vs_workstation_revised_freeze.csv`` -- nothing is carried over
from the historical 0.668/0.746/42/55 numbers. This is the single source of the
revised paper-facing statistics; docs/figures/tests read the emitted
``effectiveness_revised_stats.json`` rather than hard-coding literals.

Subset rules (spec §6):
  * ALL             : all 55 first-query cells (lp already excluded from the table).
  * high_confidence : not low_conf   (the historical high-conf gate).
  * high_conf_clean : not low_conf AND not position_sensitive. Position-sensitive
                      cells carry a descriptive balanced-batch aggregate whose
                      subsets disagree in sign; they are NOT presented as equally
                      clean position-independent evidence in this subset.

Strong workstation strategies use R_ws >= 0.30 (the report's "strongly effective"
bar); "effective on OpenWhisk" uses the category gate R_ow >= 0.10.
"""
import csv
import json
import statistics as st
from collections import defaultdict
from pathlib import Path

CMP = Path(__file__).resolve().parents[1] / "analysis/comparison"
REVISED = CMP / "effectiveness_ow_vs_workstation_revised_freeze.csv"
OUT_JSON = CMP / "effectiveness_revised_stats.json"

NEUTRAL_BAND = 0.10
STRONG_WS = 0.30
WORKLOAD_ORDER = ["YC", "YCu", "YCh01", "C", "C_hit"]


def _ranks(xs):
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    ranks = [0.0] * len(xs)
    i = 0
    while i < len(xs):
        j = i
        while j + 1 < len(xs) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def spearman(xs, ys):
    if len(xs) < 2:
        return None
    rx, ry = _ranks(xs), _ranks(ys)
    n = len(xs)
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((rx[i] - mx) * (ry[i] - my) for i in range(n))
    dx = sum((rx[i] - mx) ** 2 for i in range(n)) ** 0.5
    dy = sum((ry[i] - my) ** 2 for i in range(n)) ** 0.5
    if dx == 0 or dy == 0:
        return None
    return num / (dx * dy)


def _as_bool(s):
    return str(s).strip().lower() == "true"


def load_rows():
    rows = list(csv.DictReader(open(REVISED)))
    for r in rows:
        r["R_ws"] = float(r["R_ws"])
        r["R_ow"] = float(r["R_ow"])
        r["abs_diff"] = float(r["abs_diff"])
        r["low_conf"] = _as_bool(r["low_conf"])
        r["position_sensitive"] = _as_bool(r["position_sensitive"])
        r["sign_agree"] = _as_bool(r["sign_agree"])
    return rows


def compute(rows):
    n = len(rows)
    hi = [r for r in rows if not r["low_conf"]]
    hi_clean = [r for r in hi if not r["position_sensitive"]]

    agree = sum(1 for r in rows if r["sign_agree"])
    agree_hi = sum(1 for r in hi if r["sign_agree"])
    agree_hi_clean = sum(1 for r in hi_clean if r["sign_agree"])

    strong_ws = [r for r in rows if r["R_ws"] >= STRONG_WS]
    strong_ws_eff_ow = [r for r in strong_ws if r["R_ow"] >= NEUTRAL_BAND]

    eff_ws = [r for r in rows if r["R_ws"] >= NEUTRAL_BAND]           # category "effective"
    eff_ws_eff_ow = [r for r in eff_ws if r["R_ow"] >= NEUTRAL_BAND]

    per_wl = {}
    for wl in WORKLOAD_ORDER:
        sub = [r for r in rows if r["workload"] == wl]
        rho = spearman([r["R_ws"] for r in sub], [r["R_ow"] for r in sub])
        per_wl[wl] = {
            "n": len(sub),
            "rho": round(rho, 4) if rho is not None else None,
            "direction_agreement": f"{sum(1 for r in sub if r['sign_agree'])}/{len(sub)}",
        }

    exceptions = []
    for r in sorted([r for r in rows if not r["sign_agree"]],
                    key=lambda r: (WORKLOAD_ORDER.index(r["workload"]), r["strategy"])):
        exceptions.append({
            "workload": r["workload"], "strategy": r["strategy"],
            "R_ws": round(r["R_ws"], 4), "R_ow": round(r["R_ow"], 4),
            "cat_ws": r["cat_ws"], "cat_ow": r["cat_ow"],
            "position_sensitive": r["position_sensitive"],
            "evidence_campaign": r["evidence_campaign"],
        })

    rho_all = spearman([r["R_ws"] for r in rows], [r["R_ow"] for r in rows])
    rho_hi = spearman([r["R_ws"] for r in hi], [r["R_ow"] for r in hi])
    rho_hi_clean = spearman([r["R_ws"] for r in hi_clean], [r["R_ow"] for r in hi_clean])

    return {
        "source": REVISED.name,
        "n_cells": n,
        "n_high_confidence": len(hi),
        "n_high_conf_clean": len(hi_clean),
        "n_low_conf": n - len(hi),
        "n_position_sensitive": sum(1 for r in rows if r["position_sensitive"]),
        "direction_agreement_all": f"{agree}/{n}",
        "direction_agreement_high_confidence": f"{agree_hi}/{len(hi)}",
        "direction_agreement_high_conf_clean": f"{agree_hi_clean}/{len(hi_clean)}",
        "category_agreement_all": f"{agree}/{n}",  # category == sign_agree in this table
        "strong_ws_threshold": STRONG_WS,
        "n_strong_ws": len(strong_ws),
        "n_strong_ws_effective_on_ow": len(strong_ws_eff_ow),
        "strong_ws_agreement": f"{len(strong_ws_eff_ow)}/{len(strong_ws)}",
        "n_effective_ws": len(eff_ws),
        "n_effective_ws_effective_on_ow": len(eff_ws_eff_ow),
        "effective_ws_agreement": f"{len(eff_ws_eff_ow)}/{len(eff_ws)}",
        "rho_all": round(rho_all, 4),
        "rho_high_confidence": round(rho_hi, 4),
        "rho_high_conf_clean": round(rho_hi_clean, 4),
        "median_abs_gap": round(st.median([r["abs_diff"] for r in rows]), 4),
        "per_workload": per_wl,
        "n_exceptions": len(exceptions),
        "exceptions": exceptions,
        "coverage": "65/65",
        "pooled": False,
    }


def main():
    stats = compute(load_rows())
    with open(OUT_JSON, "w") as f:
        json.dump(stats, f, indent=2)
        f.write("\n")
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
