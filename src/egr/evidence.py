"""Evidence records: the source values behind a flag, validated against a schema."""

from __future__ import annotations

import hashlib
import json
from functools import cache
from importlib import resources
from typing import Any

import jsonschema

from egr import config
from egr.cells import Cell, Companies
from egr.plausibility import Score
from egr.rules import RuleFlag

Evidence = dict[str, Any]


@cache
def schema() -> dict[str, Any]:
    """The evidence record JSON schema shipped with the package."""
    text = (
        resources.files("egr").joinpath("schemas/evidence.schema.json").read_text(encoding="utf-8")
    )
    return dict(json.loads(text))


@cache
def _validator() -> jsonschema.Draft202012Validator:
    jsonschema.Draft202012Validator.check_schema(schema())
    return jsonschema.Draft202012Validator(schema())


def validate(record: Evidence) -> None:
    """Raise jsonschema.ValidationError if the record does not match the schema."""
    error = jsonschema.exceptions.best_match(_validator().iter_errors(record))
    if error is not None:
        raise error


def canonical(obj: Any) -> str:
    """Canonical JSON: sorted keys, no whitespace, no ASCII escaping."""
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )


def digest(obj: Any) -> str:
    """SHA-256 of the canonical JSON of obj."""
    return hashlib.sha256(canonical(obj).encode("utf-8")).hexdigest()


def _lookup(companies: Companies, cell_id: str) -> Cell:
    cik, period_end, item = cell_id.split("|")
    cell = companies[int(cik)].get(period_end, item)
    if cell is None:
        raise KeyError(cell_id)
    return cell


def source_entry(cell: Cell, value: float) -> dict[str, Any]:
    """One source value as it appears in an evidence record."""
    return {
        "cell_id": cell.cell_id,
        "item": cell.item,
        "label": config.ITEM_BY_KEY[cell.item].label,
        "element": cell.source.element,
        "period_start": cell.period_start,
        "period_end": cell.period_end,
        "ytd_months": cell.ytd_months,
        "value": value,
        "unit": "USD",
        "accession_number": cell.source.accn,
        "form": cell.source.form,
        "filed": cell.source.filed,
        "retrieved": cell.source.retrieved,
    }


def from_rule(flag: RuleFlag, companies: Companies, view: dict[str, float]) -> Evidence:
    """Evidence record of a rule flag."""
    cells = [_lookup(companies, cid) for cid in flag.cell_ids]
    record: Evidence = {
        "flag_id": f"{flag.rule}|{flag.cik}|{flag.period_end}",
        "detector": "rule",
        "rule": flag.rule,
        "rule_statement": config.RULE_LABELS[flag.rule],
        "company": {"cik": flag.cik, "name": cells[0].name},
        "period_end": flag.period_end,
        "flagged_cell_ids": list(flag.cell_ids),
        "sources": [source_entry(c, view[c.cell_id]) for c in cells],
        "computed": {k: round(v, 2) for k, v in flag.computed.items()},
    }
    validate(record)
    return record


def from_score(
    score: Score, p_value: float, companies: Companies, view: dict[str, float]
) -> Evidence:
    """Evidence record of a plausibility flag."""
    cell = _lookup(companies, score.cell_id)
    seen: list[str] = []
    for cid in [score.cell_id, *score.source_cell_ids]:
        if cid not in seen:
            seen.append(cid)
    sources = [source_entry(_lookup(companies, cid), view[cid]) for cid in seen]
    computed: dict[str, float] = {
        "prediction": round(score.prediction, 2),
        "residual": round(score.residual, 2),
        "scale": round(score.scale, 2),
        "score": score.score,
        "p_value": p_value,
        "history_n": float(score.history_n),
    }
    for name, value in score.candidates.items():
        computed[f"candidate_{name}"] = round(value, 2)
    record: Evidence = {
        "flag_id": f"P|{score.cell_id}",
        "detector": "plausibility",
        "rule": None,
        "rule_statement": None,
        "company": {"cik": cell.cik, "name": cell.name},
        "period_end": cell.period_end,
        "flagged_cell_ids": [score.cell_id],
        "sources": sources,
        "computed": computed,
    }
    validate(record)
    return record
