"""Deterministic query text from an evidence record, in the form of a comment letter.

Every number is written in full with thousands separators and every period as
a date, so that the faithfulness checker can match each one to the record.
"""

from __future__ import annotations

from datetime import date

from egr.evidence import Evidence

MONTHS = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)


def money(value: float) -> str:
    """USD amount with thousands separators, integers without decimals."""
    amount = f"{abs(int(value)):,}" if float(value).is_integer() else f"{abs(value):,.2f}"
    return f"-${amount}" if value < 0 else f"${amount}"


def long_date(iso: str) -> str:
    """2020-03-31 as March 31, 2020."""
    d = date.fromisoformat(iso)
    return f"{MONTHS[d.month - 1]} {d.day}, {d.year}"


def _source(record: Evidence, cell_id: str) -> dict[str, object]:
    for s in record["sources"]:
        if s["cell_id"] == cell_id:
            return dict(s)
    raise KeyError(cell_id)


def _opening(record: Evidence, source: dict[str, object]) -> str:
    return (
        f"We refer to the Form {source['form']} (accession number {source['accession_number']}, "
        f"filed {long_date(str(source['filed']))}) for the period ended "
        f"{long_date(record['period_end'])}."
    )


def _amount_with_span(source: dict[str, object]) -> str:
    label, value, months = (
        source["label"],
        float(str(source["value"])),
        int(str(source["ytd_months"])),
    )
    span = f" for the {months} months then ended" if months else ""
    return f"{label} of {money(value)}{span}"


def template(record: Evidence) -> str:
    """The query sentence(s) for a rule or plausibility flag."""
    first = record["flagged_cell_ids"][0]
    main = _source(record, first)
    opening = _opening(record, main)
    computed = record["computed"]
    tol = (
        f", which exceeds the tolerance of {money(computed['tolerance'])}."
        if "tolerance" in computed
        else ""
    )
    if record["detector"] == "rule":
        rule = record["rule"]
        sources = {s["item"]: s for s in record["sources"]}
        if rule == "R1":
            a, b = sources["assets"], sources["liabilities_and_equity"]
            body = (
                f"{_amount_with_span(a).capitalize()} differs from {_amount_with_span(b)} by "
                f"{money(computed['difference'])}{tol}"
            )
        elif rule in ("R2", "R3", "R4"):
            part, whole = record["sources"][0], record["sources"][1]
            body = (
                f"{_amount_with_span(part).capitalize()} exceeds {_amount_with_span(whole)} by "
                f"{money(computed['excess'])}{tol}"
            )
        elif rule == "R5":
            body = f"{_amount_with_span(main).capitalize()} is negative."
        elif rule == "R6":
            g, r, c = sources["gross_profit"], sources["revenue"], sources["cost_of_revenue"]
            body = (
                f"{_amount_with_span(g).capitalize()} differs by {money(computed['difference'])} "
                f"from the {money(computed['implied_gross_profit'])} implied by "
                f"{_amount_with_span(r)} less {_amount_with_span(c)}{tol}"
            )
        else:
            parts = [s for s in record["sources"] if s["item"] != "cash_change"]
            listed = ", ".join(_amount_with_span(s) for s in parts)
            body = (
                f"{_amount_with_span(sources['cash_change']).capitalize()} differs by "
                f"{money(computed['difference'])} from the sum of "
                f"{money(computed['sum_of_components'])} of {listed}{tol}"
            )
        request = "Please explain the difference or tell us how you intend to revise the filing."
    else:
        body = (
            f"{_amount_with_span(main).capitalize()} is {money(abs(computed['residual']))} away "
            f"from the {money(computed['prediction'])} implied by the company's earlier filings "
            f"and the other items of the period, more than the usual spread of "
            f"{money(computed['scale'])} for this item."
        )
        request = "Please tell us how the figure was determined and whether it is correctly stated."
    return f"{opening} {body} {request}"
