"""One detection run: injection, rules, scores, p-values, rankings and evidence.

The output of a run is a flags file and an evidence file whose bytes depend
only on the input cells, the injection and the settings.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from egr import config
from egr.cells import Cell, Companies
from egr.conformal import Calibration, PValue, benjamini_hochberg, rank_by_p
from egr.evidence import Evidence, canonical, from_rule, from_score
from egr.inject import Injection, values_view
from egr.plausibility import Score, score_company
from egr.rules import RuleFlag, check_company

DETECTORS = ("nothing", "rules", "plausibility", "combined")


@dataclass
class RunResult:
    """Everything a detection run produces, before evaluation."""

    tag: str
    replicate: int
    rate: float
    cells: pd.DataFrame
    evidence: list[Evidence]
    calibration_n: dict[str, int]
    n_heldout_tested: int
    n_scored: int
    timings: dict[str, float] = field(default_factory=dict)

    @property
    def flags_json(self) -> str:
        """Canonical JSON of the rankings and rejections, the object the determinism test hashes."""
        rows = self.cells.sort_values("cell_id")
        payload = {
            "n_heldout_tested": self.n_heldout_tested,
            "cells": [
                {
                    "cell_id": r["cell_id"],
                    "rank_rules": int(r["rank_rules"]),
                    "rank_plausibility": int(r["rank_plausibility"]),
                    "rank_combined": int(r["rank_combined"]),
                    "p_num": int(r["p_num"]),
                    "p_den": int(r["p_den"]),
                    "rules": r["rules"],
                    **{
                        f"bh_{int(q * 100):02d}": bool(r[f"bh_{int(q * 100):02d}"])
                        for q in config.BH_TARGETS
                    },
                }
                for r in rows.to_dict("records")
                if r["rank_rules"]
                or r["rank_plausibility"]
                or any(r[f"bh_{int(q * 100):02d}"] for q in config.BH_TARGETS)
            ],
        }
        return canonical(payload)


def max_budget_k(n: int) -> int:
    """Flags allowed by the largest budget on n tested cells."""
    return (max(config.BUDGETS_PER_1000) * n) // 1000


def calibration_scores(companies: Companies, view: dict[str, float]) -> dict[str, list[float]]:
    """Plausibility scores of development companies under a values view, per item."""
    by_item: dict[str, list[float]] = {k: [] for k in config.TESTED_KEYS}
    for company in companies.values():
        if company.split != "development":
            continue
        for s in score_company(company, view).values():
            by_item[s.cell_id.split("|")[2]].append(s.score)
    return by_item


def run(
    companies: Companies,
    injection: Injection,
    tag: str,
    replicate: int,
    rate: float,
    calibration_from: dict[str, list[float]] | None = None,
) -> RunResult:
    """Run rules and plausibility on held-out companies and test them against the calibration.

    The calibration scores come from clean development data unless given; the
    pre-specified variant that calibrates on injected development data passes
    them in explicitly.
    """
    timings: dict[str, float] = {}
    t = time.perf_counter()
    view = values_view(companies, injection)
    heldout_companies = {cik: c for cik, c in companies.items() if c.split == "heldout"}
    rule_flags: dict[int, list[RuleFlag]] = {}
    for cik, company in heldout_companies.items():
        rule_flags[cik] = check_company(company, view)
    timings["rules"] = time.perf_counter() - t

    t = time.perf_counter()
    scores: dict[int, dict[str, Score]] = {}
    for cik, company in heldout_companies.items():
        scores[cik] = score_company(company, view)
    timings["plausibility"] = time.perf_counter() - t

    t = time.perf_counter()
    if calibration_from is None:
        calibration_from = calibration_scores(companies, values_view(companies, {}))
    calibration = {k: Calibration(v) for k, v in calibration_from.items()}
    timings["calibration"] = time.perf_counter() - t
    t = time.perf_counter()

    heldout: list[Cell] = [
        company.cells[p][item]
        for company in heldout_companies.values()
        for p in company.periods
        for item in sorted(company.cells[p])
        if company.cells[p][item].tested
    ]
    heldout_scores: dict[str, Score] = {}
    p_values: dict[str, PValue] = {}
    for cell in heldout:
        found = scores[cell.cik].get(cell.cell_id)
        if found is None or calibration[cell.item].n == 0:
            continue
        heldout_scores[cell.cell_id] = found
        p_values[cell.cell_id] = calibration[cell.item].p_value(found.score)
    plain_scores = {k: v.score for k, v in heldout_scores.items()}
    bh_sets = {q: benjamini_hochberg(p_values, round(q * 100)) for q in config.BH_TARGETS}
    rank_plaus = rank_by_p(p_values, plain_scores)
    timings["conformal"] = time.perf_counter() - t

    t = time.perf_counter()
    cell_rules: dict[str, list[RuleFlag]] = {}
    for cik in heldout_companies:
        for flag in rule_flags[cik]:
            for cid in flag.cell_ids:
                if cid.split("|")[2] in config.TESTED_KEYS:
                    cell_rules.setdefault(cid, []).append(flag)
    rank_rules = sorted(
        cell_rules, key=lambda cid: (-max(f.violation for f in cell_rules[cid]), cid)
    )
    in_rules = set(rank_rules)
    rank_combined = rank_rules + [cid for cid in rank_plaus if cid not in in_rules]
    pos_rules = {cid: i + 1 for i, cid in enumerate(rank_rules)}
    pos_plaus = {cid: i + 1 for i, cid in enumerate(rank_plaus)}
    pos_combined = {cid: i + 1 for i, cid in enumerate(rank_combined)}

    rows: list[dict[str, Any]] = []
    for cell in heldout:
        cid = cell.cell_id
        inj = injection.get(cid)
        sc = heldout_scores.get(cid)
        p = p_values.get(cid)
        row: dict[str, Any] = {
            "cell_id": cid,
            "cik": cell.cik,
            "period_end": cell.period_end,
            "item": cell.item,
            "ytd_months": cell.ytd_months,
            "value_clean": cell.value,
            "value_used": view[cid],
            "injected": inj is not None,
            "error_type": inj.error_type if inj else "",
            "amended_changed": cell.amended_changed,
            "revised_later": cell.revised_later,
            "scored": sc is not None,
            "score": sc.score if sc else float("nan"),
            "p_value": float(p) if p is not None else float("nan"),
            "p_num": p.num if p is not None else 0,
            "p_den": p.den if p is not None else 0,
            "rules": ",".join(sorted({f.rule for f in cell_rules.get(cid, [])})),
            "rank_rules": pos_rules.get(cid, 0),
            "rank_plausibility": pos_plaus.get(cid, 0),
            "rank_combined": pos_combined.get(cid, 0),
        }
        for q in config.BH_TARGETS:
            row[f"bh_{int(q * 100):02d}"] = cid in bh_sets[q]
        rows.append(row)
    cells = pd.DataFrame(rows)

    n = len(heldout)
    k_max = max_budget_k(n)
    wanted: set[str] = set()
    for ranking in (rank_rules, rank_plaus, rank_combined):
        wanted.update(ranking[:k_max])
    for q in config.BH_TARGETS:
        wanted.update(bh_sets[q])
    evidence: dict[str, Evidence] = {}
    for cid in sorted(wanted):
        for flag in cell_rules.get(cid, []):
            record = from_rule(flag, companies, view)
            evidence.setdefault(record["flag_id"], record)
        if cid in heldout_scores:
            record = from_score(heldout_scores[cid], float(p_values[cid]), companies, view)
            evidence.setdefault(record["flag_id"], record)
    timings["evidence"] = time.perf_counter() - t

    return RunResult(
        tag=tag,
        replicate=replicate,
        rate=rate,
        cells=cells,
        evidence=[evidence[k] for k in sorted(evidence)],
        calibration_n={k: v.n for k, v in calibration.items()},
        n_heldout_tested=n,
        n_scored=len(heldout_scores),
        timings=timings,
    )


def write(result: RunResult, out_dir: Path) -> dict[str, str]:
    """Write the cells parquet, the flags json and the evidence jsonl; return their names."""
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{result.tag}_r{result.replicate:02d}"
    result.cells.to_parquet(out_dir / f"{stem}_cells.parquet", index=False)
    (out_dir / f"{stem}_flags.json").write_text(
        result.flags_json + "\n", encoding="utf-8", newline="\n"
    )
    with open(out_dir / f"{stem}_evidence.jsonl", "w", encoding="utf-8", newline="\n") as f:
        for record in result.evidence:
            f.write(canonical(record) + "\n")
    (out_dir / f"{stem}_meta.json").write_text(
        json.dumps(
            {
                "tag": result.tag,
                "replicate": result.replicate,
                "rate": result.rate,
                "n_heldout_tested": result.n_heldout_tested,
                "n_scored": result.n_scored,
                "calibration_n": result.calibration_n,
                "timings": result.timings,
            },
            indent=1,
        )
        + "\n",
        encoding="utf-8",
    )
    return {
        "cells": f"{stem}_cells.parquet",
        "flags": f"{stem}_flags.json",
        "evidence": f"{stem}_evidence.jsonl",
    }
