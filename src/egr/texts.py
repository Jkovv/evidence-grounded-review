"""Query text for a sample of flags: template, language model, checker, audit log."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from egr import config
from egr.auditlog import AuditLog
from egr.cells import Companies
from egr.evidence import Evidence, digest
from egr.faithfulness import check_text
from egr.llm import Backend, evidence_prompt, raw_prompt
from egr.querytext import template

VARIANTS = ("template", "llm_evidence", "llm_raw")


@dataclass
class TextRow:
    """One generated text and its check."""

    cell_id: str
    flag_id: str
    variant: str
    backend: str
    model: str
    prompt_hash: str
    text: str
    accepted: bool
    claims: int
    verified: int
    failures: str
    strict_ok: bool
    final_text: str
    error: str = ""


def select_flags(
    cells: pd.DataFrame, evidence: list[Evidence], n: int
) -> list[tuple[str, Evidence]]:
    """The first n cells of the combined ranking at the primary budget, with one record each."""
    k = (config.BUDGET_PRIMARY * len(cells)) // 1000
    top = cells[(cells["rank_combined"] > 0) & (cells["rank_combined"] <= k)]
    top = top.sort_values("rank_combined").head(n)
    by_cell: dict[str, list[Evidence]] = {}
    for record in evidence:
        for cid in record["flagged_cell_ids"]:
            by_cell.setdefault(cid, []).append(record)
    chosen: list[tuple[str, Evidence]] = []
    for cid in top["cell_id"]:
        records = by_cell.get(cid, [])
        rules = [r for r in records if r["detector"] == "rule"]
        plaus = [r for r in records if r["detector"] == "plausibility"]
        record = (rules or plaus or [None])[0]
        if record is not None:
            chosen.append((cid, record))
    return chosen


def raw_table(companies: Companies, cell_id: str, view: dict[str, float]) -> list[dict[str, Any]]:
    """The flagged period and the periods before it, all items, for the raw-data ablation."""
    cik, period_end, _ = cell_id.split("|")
    company = companies[int(cik)]
    i = company.periods.index(period_end)
    blocks = []
    for p in company.periods[max(0, i - config.RAW_CONTEXT_PERIODS) : i + 1]:
        any_cell = next(iter(company.cells[p].values()))
        blocks.append(
            {
                "period_end": p,
                "form": any_cell.source.form,
                "accession_number": any_cell.source.accn,
                "filed": any_cell.source.filed,
                "values": {k: view[c.cell_id] for k, c in sorted(company.cells[p].items())},
            }
        )
    return blocks


def generate_all(
    flags: list[tuple[str, Evidence]],
    companies: Companies,
    view: dict[str, float],
    backend: Backend | None,
    log: AuditLog,
) -> list[TextRow]:
    """Template and, when a backend is configured, both language-model variants for each flag."""
    rows: list[TextRow] = []
    for cid, record in flags:
        fallback = template(record)
        check = check_text(fallback, record)
        strict = check_text(fallback, record, strict=True)
        rows.append(
            TextRow(
                cid,
                record["flag_id"],
                "template",
                "template",
                "",
                "",
                fallback,
                check.accepted,
                check.claims,
                check.verified,
                "; ".join(check.failures),
                strict.accepted,
                fallback,
            )
        )
        log.append(
            "text",
            {
                "flag_id": record["flag_id"],
                "variant": "template",
                "evidence_hash": digest(record),
                "text": fallback,
                "accepted": check.accepted,
            },
        )
        if backend is None:
            continue
        for variant in ("llm_evidence", "llm_raw"):
            if variant == "llm_evidence":
                system, user = evidence_prompt(record)
            else:
                system, user = raw_prompt(record, raw_table(companies, cid, view))
            gen = backend.generate(system, user)
            check = check_text(gen.text, record)
            strict = check_text(gen.text, record, strict=True) if check.accepted else strict
            final = gen.text if check.accepted else fallback
            rows.append(
                TextRow(
                    cid,
                    record["flag_id"],
                    variant,
                    gen.backend,
                    gen.model,
                    gen.prompt_hash,
                    gen.text,
                    check.accepted,
                    check.claims,
                    check.verified,
                    "; ".join(check.failures),
                    check.accepted and strict.accepted,
                    final,
                    gen.error,
                )
            )
            log.append(
                "text",
                {
                    "flag_id": record["flag_id"],
                    "variant": variant,
                    "backend": gen.backend,
                    "model": gen.model,
                    "prompt_hash": gen.prompt_hash,
                    "evidence_hash": digest(record),
                    "text": gen.text,
                    "accepted": check.accepted,
                    "error": gen.error,
                },
            )
            if not check.accepted:
                log.append(
                    "rejection",
                    {
                        "flag_id": record["flag_id"],
                        "variant": variant,
                        "failures": check.failures,
                        "replaced_by": "template",
                    },
                )
    return rows


def summarise(rows: list[TextRow]) -> pd.DataFrame:
    """Per-variant faithfulness table."""
    frame = pd.DataFrame([asdict(r) for r in rows])
    out = []
    for variant in VARIANTS:
        part = frame[frame["variant"] == variant]
        if part.empty:
            out.append({"variant": variant, "texts": 0, "run": False})
            continue
        generated = part[part["error"] == ""]
        accepted = generated[generated["accepted"]]
        out.append(
            {
                "variant": variant,
                "run": True,
                "texts": len(part),
                "generation_errors": int((part["error"] != "").sum()),
                "claims": int(generated["claims"].sum()),
                "claims_verified_share": float(
                    generated["verified"].sum() / max(generated["claims"].sum(), 1)
                ),
                "texts_with_unverified_claim_share": float(1 - generated["accepted"].mean())
                if len(generated)
                else float("nan"),
                "rejection_rate": float(1 - part["accepted"].mean()),
                "accepted": len(accepted),
                "accepted_not_exact_share": float(1 - accepted["strict_ok"].mean())
                if len(accepted)
                else float("nan"),
                "model": part["model"].iloc[0],
                "backend": part["backend"].iloc[0],
            }
        )
    return pd.DataFrame(out)


def write_rows(rows: list[TextRow], path: Path) -> None:
    """All texts and checks as JSON lines."""
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(asdict(r), ensure_ascii=False) + "\n")
