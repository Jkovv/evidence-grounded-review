"""Build the as-reported cell table, the amendment ground truth and the split.

Reads the raw company facts and submissions written by data/download_sec.py and
writes parquet files under the processed directory. The rules for choosing the
filing of record, the element per item and the year-to-date fact follow
docs/analysis_plan.md, section Data.
"""

from __future__ import annotations

import json
import random
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from egr import config
from egr.config import Item

Fact = dict[str, Any]


@dataclass
class Filing:
    """One accession number with its form, filing date and own period end."""

    accn: str
    form: str
    filed: str
    own_end: str


def _days(start: str, end: str) -> int:
    return (date.fromisoformat(end) - date.fromisoformat(start)).days


def _months(start: str, end: str) -> int:
    return round(_days(start, end) / 30.4375)


def differs(
    a: float,
    b: float,
    rel: float = config.AMENDMENT_REL_TOL,
    abs_tol: float = config.AMENDMENT_ABS_TOL,
) -> bool:
    """True when two values differ by more than rounding would explain."""
    return abs(a - b) > rel * max(abs(a), abs(b)) and abs(a - b) > abs_tol


def usd_facts(facts: dict[str, Any], element: str) -> list[Fact]:
    """USD facts of one us-gaap element, in the order the SEC lists them."""
    return list(facts.get("us-gaap", {}).get(element, {}).get("units", {}).get("USD", []))


def filings_by_accn(facts: dict[str, Any]) -> dict[str, Filing]:
    """Every accession number that reports total assets, with its own period end."""
    out: dict[str, Filing] = {}
    for f in usd_facts(facts, "Assets"):
        cur = out.get(f["accn"])
        if cur is None or f["end"] > cur.own_end:
            out[f["accn"]] = Filing(f["accn"], f["form"], f["filed"], f["end"])
    return out


def filings_of_record(filings: dict[str, Filing]) -> dict[str, Filing]:
    """Own period end to the earliest filed original filing with that end."""
    record: dict[str, Filing] = {}
    for fl in sorted(filings.values(), key=lambda x: (x.filed, x.accn)):
        if fl.form in config.ORIGINAL_FORMS and fl.own_end not in record:
            record[fl.own_end] = fl
    return record


def choose_element(facts: dict[str, Any], item: Item) -> str | None:
    """The element with the most facts from original filings, first in the list on ties."""
    best, best_n = None, 0
    for element in item.elements:
        n = sum(1 for f in usd_facts(facts, element) if f["form"] in config.ORIGINAL_FORMS)
        if n > best_n:
            best, best_n = element, n
    return best


def pick_fact(facts_of_accn: list[Fact], end: str, instant: bool) -> Fact | None:
    """The fact of a filing for one period end: the instant, or the longest duration."""
    if instant:
        for f in facts_of_accn:
            if f["end"] == end and "start" not in f:
                return f
        return None
    best: Fact | None = None
    for f in facts_of_accn:
        if f["end"] != end or "start" not in f:
            continue
        days = _days(f["start"], f["end"])
        if days > config.MAX_DURATION_DAYS or days <= 0:
            continue
        if best is None or days > _days(best["start"], best["end"]):
            best = f
    return best


def company_cells(cik: int, facts: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """All cells of one company plus the element chosen per item."""
    filings = filings_by_accn(facts)
    record = filings_of_record(filings)
    periods = sorted(record)
    name = facts.get("entityName", "")
    elements: dict[str, str] = {}
    rows: list[dict[str, Any]] = []
    for item in config.ITEMS:
        element = choose_element(facts, item)
        if element is None:
            continue
        elements[item.key] = element
        by_accn: dict[str, list[Fact]] = defaultdict(list)
        for f in usd_facts(facts, element):
            by_accn[f["accn"]].append(f)
        amendments = sorted(
            (fl for fl in filings.values() if fl.form in config.AMENDED_FORMS),
            key=lambda x: (x.filed, x.accn),
        )
        for end in periods:
            fl = record[end]
            fact = pick_fact(by_accn.get(fl.accn, []), end, item.instant)
            if fact is None:
                continue
            start = fact.get("start")
            row: dict[str, Any] = {
                "cik": cik,
                "name": name,
                "period_end": end,
                "period_start": start or "",
                "ytd_months": 0 if item.instant or start is None else _months(start, end),
                "item": item.key,
                "element": element,
                "value": float(fact["val"]),
                "accn": fl.accn,
                "form": fl.form,
                "filed": fl.filed,
                "amended_changed": False,
                "amended_value": float("nan"),
                "amended_accn": "",
                "amended_filed": "",
                "revised_later": False,
            }
            for am in amendments:
                if am.own_end != end:
                    continue
                am_fact = _same_period(by_accn.get(am.accn, []), fact)
                if am_fact is None:
                    continue
                row["amended_value"] = float(am_fact["val"])
                row["amended_accn"] = am.accn
                row["amended_filed"] = am.filed
                row["amended_changed"] = differs(row["value"], row["amended_value"])
                break
            for other_accn, other_facts in by_accn.items():
                other = filings.get(other_accn)
                if (
                    other is None
                    or other.form not in config.ORIGINAL_FORMS
                    or other.filed <= fl.filed
                ):
                    continue
                later = _same_period(other_facts, fact)
                if later is not None and differs(row["value"], float(later["val"])):
                    row["revised_later"] = True
                    break
            rows.append(row)
    return rows, elements


def _same_period(facts_of_accn: list[Fact], fact: Fact) -> Fact | None:
    for f in facts_of_accn:
        if f["end"] == fact["end"] and f.get("start") == fact.get("start"):
            return f
    return None


def nonreliance_dates(sub_dir: Path, cik: int) -> list[str]:
    """Filing dates of 8-K forms whose items include 4.02, from all submission files."""
    main_path = sub_dir / f"CIK{cik:010d}.json"
    if not main_path.exists():
        return []
    main = json.loads(main_path.read_text(encoding="utf-8"))
    blocks = [main["filings"]["recent"]]
    for part in main["filings"].get("files", []):
        path = sub_dir / part["name"]
        if path.exists():
            blocks.append(json.loads(path.read_text(encoding="utf-8")))
    dates: list[str] = []
    for block in blocks:
        for form, items, filed in zip(
            block["form"], block["items"], block["filingDate"], strict=True
        ):
            if form.startswith("8-K") and "4.02" in (items or "").split(","):
                dates.append(filed)
    return sorted(set(dates))


def make_split(ciks: list[int]) -> dict[int, str]:
    """Half development, half held out, drawn with the fixed seed from the sorted list."""
    ordered = sorted(ciks)
    rng = random.Random(config.SEED + 1)
    rng.shuffle(ordered)
    n_dev = round(len(ordered) * config.DEV_SHARE)
    return {cik: ("development" if i < n_dev else "heldout") for i, cik in enumerate(ordered)}


def prepare(raw_dir: Path | None = None, out_dir: Path | None = None) -> dict[str, Any]:
    """Run the whole preparation and return the summary that is also written to disk."""
    raw_dir = raw_dir or config.RAW_DIR
    out_dir = out_dir or config.PROCESSED_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    universe: list[int] = json.loads((out_dir / "universe.json").read_text(encoding="utf-8"))
    all_rows: list[dict[str, Any]] = []
    companies: list[dict[str, Any]] = []
    dropped: list[int] = []
    nonreliance: list[dict[str, Any]] = []
    for cik in universe:
        path = raw_dir / "companyfacts" / f"CIK{cik:010d}.json"
        if not path.exists():
            dropped.append(cik)
            continue
        facts = json.loads(path.read_text(encoding="utf-8"))["facts"]
        facts["entityName"] = json.loads(path.read_text(encoding="utf-8")).get("entityName", "")
        rows, elements = company_cells(cik, facts)
        n_periods = len({r["period_end"] for r in rows if r["item"] == "assets"})
        if n_periods < config.MIN_PERIODS:
            dropped.append(cik)
            continue
        all_rows.extend(rows)
        companies.append(
            {
                "cik": cik,
                "name": facts["entityName"],
                "n_periods": n_periods,
                "elements": json.dumps(elements),
            }
        )
        for d in nonreliance_dates(raw_dir / "submissions", cik):
            nonreliance.append({"cik": cik, "filing_date": d})
    split = make_split([c["cik"] for c in companies])
    for c in companies:
        c["split"] = split[c["cik"]]
    cells = pd.DataFrame(all_rows)
    cells["split"] = cells["cik"].map(split)
    cells = cells.sort_values(["cik", "period_end", "item"], kind="mergesort").reset_index(
        drop=True
    )
    cells.to_parquet(out_dir / "cells.parquet", index=False)
    pd.DataFrame(companies).to_parquet(out_dir / "companies.parquet", index=False)
    pd.DataFrame(nonreliance, columns=["cik", "filing_date"]).to_parquet(
        out_dir / "nonreliance.parquet", index=False
    )
    summary = {
        "companies_in_universe": len(universe),
        "companies_kept": len(companies),
        "companies_dropped": dropped,
        "development": sum(1 for s in split.values() if s == "development"),
        "heldout": sum(1 for s in split.values() if s == "heldout"),
        "cells": len(cells),
        "tested_cells": int(cells["item"].isin(config.TESTED_KEYS).sum()),
        "amended_changed": int(cells["amended_changed"].sum()),
        "with_amended_value": int(cells["amended_value"].notna().sum()),
        "revised_later": int(cells["revised_later"].sum()),
        "nonreliance_8k": len(nonreliance),
        "companies_with_nonreliance": len({r["cik"] for r in nonreliance}),
        "periods_per_company_median": float(
            pd.Series([c["n_periods"] for c in companies]).median()
        ),
    }
    (out_dir / "prepare_summary.json").write_text(
        json.dumps(summary, indent=1) + "\n", encoding="utf-8"
    )
    return summary
