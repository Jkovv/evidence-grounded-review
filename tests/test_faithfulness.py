import pytest

from egr.evidence import from_rule, from_score
from egr.faithfulness import check_text, mentioned_items, split_sentences
from egr.inject import values_view
from egr.plausibility import score_company
from egr.querytext import long_date, money, template
from egr.rules import check_period


@pytest.fixture
def rule_record(companies):
    company = companies[1006]
    period = company.periods[6]
    view = values_view(companies, {})
    cell = company.get(period, "assets")
    view[cell.cell_id] = cell.value * 2
    flag = check_period(company, period, view)[0]
    return from_rule(flag, companies, view)


@pytest.fixture
def score_record(companies):
    company = companies[1007]
    view = values_view(companies, {})
    scores = score_company(company, view)
    score = scores[f"1007|{company.periods[-1]}|cfo"]
    return from_score(score, 0.003, companies, view)


@pytest.mark.req("REQ-008")
def test_template_text_passes_the_checker(rule_record, score_record):
    for record in (rule_record, score_record):
        text = template(record)
        check = check_text(text, record)
        assert check.accepted, check.failures
        assert check.claims > 3 and check.verified == check.claims
        assert check_text(text, record, strict=True).accepted


@pytest.mark.req("REQ-009")
def test_a_number_not_in_the_evidence_is_rejected(rule_record):
    text = template(rule_record) + " The difference amounts to $12,345,678."
    check = check_text(text, rule_record)
    assert not check.accepted
    assert any("12,345,678" in f for f in check.failures)


@pytest.mark.req("REQ-009")
def test_rounded_numbers_with_units_are_accepted_but_not_strictly(rule_record):
    value = rule_record["sources"][0]["value"]
    millions = f"${value / 1e6:,.1f} million"
    text = f"Total assets were reported at {millions}."
    assert check_text(text, rule_record).accepted
    assert not check_text(text, rule_record, strict=True).accepted


@pytest.mark.req("REQ-009")
def test_percentages_are_never_verifiable(rule_record):
    assert not check_text("Total assets differ by 0.5% from the total.", rule_record).accepted


@pytest.mark.req("REQ-010")
def test_a_line_item_not_in_the_evidence_is_rejected(rule_record):
    text = template(rule_record) + " Net income for the period was also reported."
    check = check_text(text, rule_record)
    assert not check.accepted
    assert any("net income" in f for f in check.failures)


@pytest.mark.req("REQ-011")
def test_a_period_not_in_the_evidence_is_rejected(rule_record):
    text = "We refer to the Form 10-Q for the period ended March 31, 1999."
    check = check_text(text, rule_record)
    assert not check.accepted
    assert any("March 31, 1999" in f for f in check.failures)
    iso = "The period ended 1999-03-31 is also affected."
    assert not check_text(iso, rule_record).accepted


@pytest.mark.req("REQ-012")
def test_empty_text_is_rejected(rule_record):
    assert not check_text("", rule_record).accepted


def test_sentence_split_protects_abbreviations():
    parts = split_sentences("We refer to Acme Inc. and its filing. Please explain.")
    assert parts == ["We refer to Acme Inc. and its filing.", "Please explain."]


def test_longest_item_phrase_wins():
    found = mentioned_items("total liabilities and stockholders' equity and current assets")
    assert [k for _, k in found] == ["liabilities_and_equity", "assets_current"]


def test_money_and_dates():
    assert money(1234567.0) == "$1,234,567"
    assert money(-1234.5) == "-$1,234.50"
    assert long_date("2020-03-31") == "March 31, 2020"
