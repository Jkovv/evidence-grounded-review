"""Evaluation on held-out companies: budgets, false-flag rates, amendments, bootstrap.

Reads the per-replicate cell tables written by the detect step and writes the
tables in results/tables and results/summary.json. Intervals are percentile
intervals from a bootstrap over held-out companies, the same resamples for
every detector, averaged over replicates.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from egr import config
from egr.detect import DETECTORS

RANK_COLUMN = {
    "rules": "rank_rules",
    "plausibility": "rank_plausibility",
    "combined": "rank_combined",
}
TAGS = {"primary": config.ERROR_RATE} | {f"sens{r}": r for r in config.ERROR_RATES_SENSITIVITY}


@dataclass
class Run:
    """One replicate's cell table and metadata."""

    tag: str
    replicate: int
    cells: pd.DataFrame
    meta: dict[str, Any]


def load_runs(cells_dir: Path, tag: str) -> list[Run]:
    """All replicates of a tag, in replicate order."""
    runs = []
    for path in sorted(cells_dir.glob(f"{tag}_r*_cells.parquet")):
        replicate = int(path.stem.split("_r")[1].split("_")[0])
        meta = json.loads(
            path.with_name(f"{tag}_r{replicate:02d}_meta.json").read_text(encoding="utf-8")
        )
        runs.append(Run(tag, replicate, pd.read_parquet(path), meta))
    return runs


def company_weights(n_companies: int, n_boot: int, seed: int) -> np.ndarray:
    """Bootstrap multiplicities of each company, one row per resample, row 0 is the data."""
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, n_companies, size=(n_boot, n_companies))
    weights = np.zeros((n_boot + 1, n_companies), dtype=np.float64)
    weights[0] = 1.0
    for b in range(n_boot):
        weights[b + 1] = np.bincount(draws[b], minlength=n_companies)
    return weights


def interval(values: np.ndarray) -> tuple[float, float]:
    """2.5 and 97.5 percentiles over resamples (rows 1..), ignoring NaN."""
    boot = values[1:]
    boot = boot[~np.isnan(boot)]
    if boot.size == 0:
        return float("nan"), float("nan")
    return float(np.percentile(boot, 2.5)), float(np.percentile(boot, 97.5))


class BudgetEvaluator:
    """Weighted top-k metrics of a ranking for every bootstrap resample at once."""

    def __init__(
        self, cells: pd.DataFrame, target: str, weights: np.ndarray, companies: list[int]
    ) -> None:
        self.weights = weights
        index = {cik: i for i, cik in enumerate(companies)}
        self.comp = cells["cik"].map(index).to_numpy()
        self.target = cells[target].to_numpy(dtype=bool)
        self.types = (
            cells["error_type"].to_numpy() if "error_type" in cells else np.array([""] * len(cells))
        )
        n_cells_c = np.bincount(self.comp, minlength=len(companies))
        n_target_c = np.bincount(self.comp, weights=self.target, minlength=len(companies))
        self.n_total = weights @ n_cells_c
        self.n_target = weights @ n_target_c
        self.n_target_type = {
            t: weights
            @ np.bincount(
                self.comp, weights=(self.target & (self.types == t)), minlength=len(companies)
            )
            for t in config.ERROR_TYPES
        }
        self.cells = cells

    def at_budget(self, detector: str, budget: int) -> dict[str, np.ndarray]:
        """Caught, flags raised and budget size for every resample."""
        n_boot = self.weights.shape[0]
        k = np.floor(budget * self.n_total / 1000)
        out = {
            "k": k,
            "caught": np.zeros(n_boot),
            "flags": np.zeros(n_boot),
            **{f"caught_{t}": np.zeros(n_boot) for t in config.ERROR_TYPES},
        }
        if detector == "nothing":
            return out
        col = RANK_COLUMN[detector]
        ranked = self.cells[self.cells[col] > 0].sort_values(col)
        limit = int(min(len(ranked), 6 * k.max() + 1000))
        ranked = ranked.head(limit)
        if ranked.empty:
            return out
        positions = self.cells.index.get_indexer(ranked.index)
        comp = self.comp[positions]
        target = self.target[positions]
        types = self.types[positions]
        w = self.weights[:, comp]
        cum = np.cumsum(w, axis=1)
        taken = (cum <= k[:, None]).sum(axis=1)
        cum_target = np.cumsum(w * target, axis=1)
        idx = np.maximum(taken - 1, 0)
        rows = np.arange(n_boot)
        has = taken > 0
        out["caught"] = np.where(has, cum_target[rows, idx], 0.0)
        out["flags"] = np.where(has, cum[rows, idx], 0.0)
        for t in config.ERROR_TYPES:
            cum_t = np.cumsum(w * (target & (types == t)), axis=1)
            out[f"caught_{t}"] = np.where(has, cum_t[rows, idx], 0.0)
        return out


def budget_tables(
    runs: list[Run], target: str, weights: np.ndarray, companies: list[int]
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Metrics, recall by type and paired differences for every budget and detector."""
    per_run = {(r.replicate): BudgetEvaluator(r.cells, target, weights, companies) for r in runs}
    metric_rows, type_rows, diff_rows = [], [], []
    for budget in config.BUDGETS_PER_1000:
        stats: dict[str, dict[str, np.ndarray]] = {}
        for detector in DETECTORS:
            acc: dict[str, list[np.ndarray]] = {
                "epf": [],
                "precision": [],
                "recall": [],
                "flags": [],
                "k": [],
            }
            acc_type: dict[str, list[np.ndarray]] = {t: [] for t in config.ERROR_TYPES}
            for ev in per_run.values():
                res = ev.at_budget(detector, budget)
                with np.errstate(invalid="ignore", divide="ignore"):
                    acc["epf"].append(res["caught"] / res["k"])
                    acc["precision"].append(res["caught"] / res["flags"])
                    acc["recall"].append(res["caught"] / ev.n_target)
                    acc["flags"].append(res["flags"])
                    acc["k"].append(res["k"])
                    for t in config.ERROR_TYPES:
                        acc_type[t].append(res[f"caught_{t}"] / ev.n_target_type[t])
            stats[detector] = {name: np.nanmean(np.vstack(v), axis=0) for name, v in acc.items()}
            row: dict[str, Any] = {
                "budget_per_1000": budget,
                "detector": detector,
                "flags_budgeted": float(stats[detector]["k"][0]),
                "flags_raised": float(stats[detector]["flags"][0]),
            }
            for name in ("epf", "precision", "recall"):
                v = stats[detector][name]
                lo, hi = interval(v)
                label = {
                    "epf": "errors_per_budgeted_flag",
                    "precision": "precision",
                    "recall": "recall",
                }[name]
                row[label], row[f"{label}_lo"], row[f"{label}_hi"] = float(v[0]), lo, hi
            metric_rows.append(row)
            for t in config.ERROR_TYPES:
                v = np.nanmean(np.vstack(acc_type[t]), axis=0)
                lo, hi = interval(v)
                type_rows.append(
                    {
                        "budget_per_1000": budget,
                        "detector": detector,
                        "error_type": t,
                        "recall": float(v[0]),
                        "recall_lo": lo,
                        "recall_hi": hi,
                    }
                )
        for a, b in (
            ("combined", "rules"),
            ("plausibility", "rules"),
            ("combined", "plausibility"),
        ):
            for name, label in (("epf", "errors_per_budgeted_flag"), ("recall", "recall")):
                d = stats[a][name] - stats[b][name]
                lo, hi = interval(d)
                diff_rows.append(
                    {
                        "budget_per_1000": budget,
                        "comparison": f"{a} minus {b}",
                        "metric": label,
                        "difference": float(d[0]),
                        "lo": lo,
                        "hi": hi,
                        "share_resamples_positive": float(np.mean(d[1:] > 0)),
                    }
                )
    return pd.DataFrame(metric_rows), pd.DataFrame(type_rows), pd.DataFrame(diff_rows)


def false_flag_table(
    runs: list[Run], weights: np.ndarray, companies: list[int], label: str
) -> pd.DataFrame:
    """Achieved false-flag rate against target for the BH flags, alone and with the rules."""
    index = {cik: i for i, cik in enumerate(companies)}
    rows = []
    for q in config.BH_TARGETS:
        col = f"bh_{int(q * 100):02d}"
        for detector in ("plausibility", "combined"):
            ffr, recall, flags, false = [], [], [], []
            for r in runs:
                cells = r.cells
                flagged = cells[col].to_numpy(dtype=bool)
                if detector == "combined":
                    flagged = flagged | (cells["rank_rules"].to_numpy() > 0)
                true = (cells["injected"] | cells["amended_changed"]).to_numpy(dtype=bool)
                comp = cells["cik"].map(index).to_numpy()
                n = len(companies)
                w_flags = weights @ np.bincount(comp, weights=flagged, minlength=n)
                w_false = weights @ np.bincount(comp, weights=flagged & ~true, minlength=n)
                w_true = weights @ np.bincount(comp, weights=true, minlength=n)
                w_caught = weights @ np.bincount(comp, weights=flagged & true, minlength=n)
                with np.errstate(invalid="ignore", divide="ignore"):
                    ffr.append(w_false / w_flags)
                    recall.append(w_caught / w_true)
                flags.append(w_flags)
                false.append(w_false)
            f = np.nanmean(np.vstack(ffr), axis=0)
            rc = np.nanmean(np.vstack(recall), axis=0)
            lo, hi = interval(f)
            rows.append(
                {
                    "calibration": label,
                    "target": q,
                    "detector": detector,
                    "flags": float(np.mean(np.vstack(flags), axis=0)[0]),
                    "false_flags": float(np.mean(np.vstack(false), axis=0)[0]),
                    "achieved_false_flag_rate": float(f[0]),
                    "lo": lo,
                    "hi": hi,
                    "recall_of_errors": float(rc[0]),
                    "replicates": len(runs),
                }
            )
    return pd.DataFrame(rows)


def amendment_tables(
    clean: Run, weights: np.ndarray, companies: list[int], nonreliance: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Recall and enrichment of amended cells at each budget, and the non-reliance comparison."""
    cells = clean.cells
    base_rate = float(cells["amended_changed"].mean())
    revised_rate = float(cells["revised_later"].mean())
    ev_amended = BudgetEvaluator(cells, "amended_changed", weights, companies)
    ev_revised = BudgetEvaluator(cells, "revised_later", weights, companies)
    rows = []
    for budget in config.BUDGETS_PER_1000:
        for detector in DETECTORS:
            a = ev_amended.at_budget(detector, budget)
            v = ev_revised.at_budget(detector, budget)
            with np.errstate(invalid="ignore", divide="ignore"):
                recall = a["caught"] / ev_amended.n_target
                share = a["caught"] / a["flags"]
                enrichment = share / (ev_amended.n_target / ev_amended.n_total)
                share_rev = v["caught"] / v["flags"]
                enrich_rev = share_rev / (ev_revised.n_target / ev_revised.n_total)
            lo, hi = interval(recall)
            elo, ehi = interval(enrichment)
            rlo, rhi = interval(enrich_rev)
            rows.append(
                {
                    "budget_per_1000": budget,
                    "detector": detector,
                    "flags": float(a["flags"][0]),
                    "amended_among_flags": float(a["caught"][0]),
                    "amended_total": float(ev_amended.n_target[0]),
                    "recall_amended": float(recall[0]),
                    "recall_lo": lo,
                    "recall_hi": hi,
                    "share_amended_among_flags": float(share[0]),
                    "base_rate_amended": base_rate,
                    "enrichment_amended": float(enrichment[0]),
                    "enrichment_lo": elo,
                    "enrichment_hi": ehi,
                    "share_revised_among_flags": float(share_rev[0]),
                    "base_rate_revised": revised_rate,
                    "enrichment_revised": float(enrich_rev[0]),
                    "enrichment_revised_lo": rlo,
                    "enrichment_revised_hi": rhi,
                }
            )
    k = (config.BUDGET_PRIMARY * len(cells)) // 1000
    flagged = (cells["rank_combined"] > 0) & (cells["rank_combined"] <= k)
    end = pd.to_datetime(cells["period_end"])
    under = np.zeros(len(cells), dtype=bool)
    for cik, group in nonreliance.groupby("cik"):
        mask = (cells["cik"] == cik).to_numpy()
        if not mask.any():
            continue
        for d in pd.to_datetime(group["filing_date"]):
            window = (end > d - pd.DateOffset(months=config.NON_RELIANCE_WINDOW_MONTHS)) & (
                end <= d
            )
            under |= mask & window.to_numpy()
    nr_rows = []
    for label, sel in (("under_non_reliance", under), ("other", ~under)):
        nr_rows.append(
            {
                "company_periods": label,
                "cells": int(sel.sum()),
                "flag_rate_combined_primary_budget": float(flagged[sel].mean())
                if sel.any()
                else float("nan"),
                "amended_rate": float(cells.loc[sel, "amended_changed"].mean())
                if sel.any()
                else float("nan"),
            }
        )
    return pd.DataFrame(rows), pd.DataFrame(nr_rows)


def runtime_table(all_runs: dict[str, list[Run]]) -> pd.DataFrame:
    """Seconds per stage, averaged over replicates of each tag."""
    rows = []
    for tag, runs in all_runs.items():
        if not runs:
            continue
        stages = sorted({s for r in runs for s in r.meta["timings"]})
        n = float(np.mean([r.meta["n_heldout_tested"] for r in runs]))
        row: dict[str, Any] = {"tag": tag, "replicates": len(runs), "heldout_tested_cells": n}
        total = 0.0
        for s in stages:
            v = float(np.mean([r.meta["timings"][s] for r in runs]))
            row[f"seconds_{s}"] = v
            total += v
        row["seconds_total"] = total
        row["seconds_per_1000_heldout_cells"] = total / n * 1000
        rows.append(row)
    return pd.DataFrame(rows)


def evaluate(
    results_dir: Path = config.RESULTS_DIR, processed_dir: Path = config.PROCESSED_DIR
) -> dict[str, Any]:
    """Run the whole evaluation and write tables and the summary."""
    cells_dir = results_dir / "cells"
    tables = results_dir / "tables"
    tables.mkdir(parents=True, exist_ok=True)
    all_runs = {tag: load_runs(cells_dir, tag) for tag in TAGS}
    clean_runs = load_runs(cells_dir, "clean")
    injcal_runs = load_runs(cells_dir, "primary-injectedcal")
    primary = all_runs["primary"]
    if not primary or not clean_runs:
        raise FileNotFoundError("run detect first")
    companies = sorted(primary[0].cells["cik"].unique().tolist())
    weights = company_weights(len(companies), config.N_BOOTSTRAP, config.SEED)
    summary: dict[str, Any] = {"heldout_companies": len(companies), "bootstrap": config.N_BOOTSTRAP}

    metric_frames, type_frames, diff_frames = [], [], []
    for tag, runs in all_runs.items():
        if not runs:
            continue
        m, ty, d = budget_tables(runs, "injected", weights, companies)
        for frame in (m, ty, d):
            frame.insert(0, "error_rate", TAGS[tag])
            frame.insert(1, "replicates", len(runs))
        metric_frames.append(m)
        type_frames.append(ty)
        diff_frames.append(d)
    metrics = pd.concat(metric_frames, ignore_index=True)
    by_type = pd.concat(type_frames, ignore_index=True)
    diffs = pd.concat(diff_frames, ignore_index=True)
    metrics.to_csv(tables / "budget_metrics.csv", index=False)
    by_type.to_csv(tables / "recall_by_type.csv", index=False)
    diffs.to_csv(tables / "budget_differences.csv", index=False)

    ffr = false_flag_table(primary, weights, companies, "clean development data")
    if injcal_runs:
        ffr = pd.concat(
            [
                ffr,
                false_flag_table(
                    injcal_runs, weights, companies, "injected development data (as pre-specified)"
                ),
            ],
            ignore_index=True,
        )
    ffr.to_csv(tables / "false_flag_rate.csv", index=False)

    nonreliance = pd.read_parquet(processed_dir / "nonreliance.parquet")
    amendments, nr = amendment_tables(clean_runs[0], weights, companies, nonreliance)
    amendments.to_csv(tables / "amendments.csv", index=False)
    nr.to_csv(tables / "non_reliance.csv", index=False)

    runtime = runtime_table({**all_runs, "clean": clean_runs})
    runtime.to_csv(tables / "runtime.csv", index=False)

    prim = metrics[
        (metrics["error_rate"] == config.ERROR_RATE)
        & (metrics["budget_per_1000"] == config.BUDGET_PRIMARY)
    ]
    pdiff = diffs[
        (diffs["error_rate"] == config.ERROR_RATE)
        & (diffs["budget_per_1000"] == config.BUDGET_PRIMARY)
    ]
    summary["primary"] = {
        "budget_per_1000": config.BUDGET_PRIMARY,
        "error_rate": config.ERROR_RATE,
        "errors_per_budgeted_flag": {
            r.detector: r.errors_per_budgeted_flag for r in prim.itertuples()
        },
        "recall": {r.detector: r.recall for r in prim.itertuples()},
        "differences": {
            r.comparison: {"metric": r.metric, "difference": r.difference, "lo": r.lo, "hi": r.hi}
            for r in pdiff.itertuples()
        },
    }
    summary["false_flag_rate"] = ffr.to_dict(orient="records")
    summary["amendments_primary_budget"] = amendments[
        amendments["budget_per_1000"] == config.BUDGET_PRIMARY
    ].to_dict(orient="records")
    summary["non_reliance"] = nr.to_dict(orient="records")
    summary["runtime"] = runtime.to_dict(orient="records")
    summary["prepare"] = json.loads(
        (processed_dir / "prepare_summary.json").read_text(encoding="utf-8")
    )
    summary["injected_per_replicate"] = float(np.mean([r.cells["injected"].sum() for r in primary]))
    summary["heldout_tested_cells"] = int(primary[0].meta["n_heldout_tested"])
    summary["heldout_scored_share"] = float(
        primary[0].meta["n_scored"] / primary[0].meta["n_heldout_tested"]
    )
    (results_dir / "summary.json").write_text(
        json.dumps(summary, indent=1, default=float) + "\n", encoding="utf-8"
    )
    return summary
