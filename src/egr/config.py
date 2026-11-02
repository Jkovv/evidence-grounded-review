"""Settings, mirroring docs/analysis_plan.md.

Everything numeric that the plan fixes lives here so that the code and the plan
can be compared line by line.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
QUICK = os.environ.get("EGR_QUICK") == "1"
DATA_DIR = Path(os.environ.get("EGR_DATA_DIR", ROOT / "data"))
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / ("processed-quick" if QUICK else "processed")
MANIFEST_PATH = DATA_DIR / ("manifest-quick.json" if QUICK else "manifest.json")
RESULTS_DIR = ROOT / ("results-quick" if QUICK else "results")
TABLES_DIR = RESULTS_DIR / "tables"
FIGURES_DIR = RESULTS_DIR / "figures"
CELLS_DIR = RESULTS_DIR / "cells"
AUDIT_DIR = RESULTS_DIR / "audit"

SEED = 20261102

# SEC access
SEC_BASE = "https://data.sec.gov"
USER_AGENT = os.environ.get("EGR_USER_AGENT", "Julia Kowalczuk j.kowalczuk326@gmail.com")
MIN_REQUEST_INTERVAL = 0.15  # seconds; the SEC allows 10 requests per second

# universe
FRAME_EARLY = "CY2012Q4I"
FRAME_LATE = "CY2023Q4I"
MIN_ASSETS = 1e8
N_COMPANIES = 24 if QUICK else 400
MIN_PERIODS = 20

# split: half development, half held out
DEV_SHARE = 0.5

# injection
N_REPLICATES = 2 if QUICK else 10
ERROR_RATE = 0.01
ERROR_RATES_SENSITIVITY = (0.005, 0.02)
ERROR_TYPES = (
    "sign_flip",
    "scale_slip",
    "digit_transposition",
    "copy_forward",
    "cross_company_swap",
)
SCALE_FACTOR = 1000.0
TRANSPOSITION_DIGITS = 4

# rules
REL_TOL = 0.001
ABS_TOL = 1000.0
CASHFLOW_REL_TOL = 0.01

# plausibility
MIN_HISTORY = 4
SCALE_FLOOR_SHARE = 0.02
SCALE_FLOOR_ABS = 1000.0
NO_HISTORY_SCALE_SHARE = 0.10
SCORE_DIGITS = 9

# error control
BH_TARGETS = (0.05, 0.10, 0.20)
BH_PRIMARY = 0.10
BUDGETS_PER_1000 = (2, 5, 10, 20)
BUDGET_PRIMARY = 10

# evaluation
N_BOOTSTRAP = 200 if QUICK else 1000
NON_RELIANCE_WINDOW_MONTHS = 24
AMENDMENT_REL_TOL = 0.001
AMENDMENT_ABS_TOL = 1000.0

# query text
N_TEXT_FLAGS = 20 if QUICK else 100
N_TEXT_EXAMPLES = 50
RAW_CONTEXT_PERIODS = 4
# "", "anthropic", "openai_compatible" or "ollama"
LLM_BACKEND = os.environ.get("EGR_LLM_BACKEND", "")
LLM_MODEL = os.environ.get("EGR_LLM_MODEL", "")
LLM_BASE_URL = os.environ.get("EGR_LLM_BASE_URL", "http://localhost:11434/v1")
LLM_MAX_TOKENS = 400


@dataclass(frozen=True)
class Item:
    """One line item of the fixed set.

    Attributes:
        key: short name used in tables and evidence records.
        label: human readable label used in query text.
        statement: balance_sheet, income_statement or cash_flow.
        instant: True for balance sheet items, False for durations.
        elements: us-gaap elements to try, in order of preference.
        nonnegative: whether rule R5 applies.
        partner: key of the partner item for the ratio prediction, or None.
        partner_fallback: second choice partner when the first is missing.
        tested: False for context items that are never flagged.
        synonyms: other names the faithfulness checker accepts for the item.
    """

    key: str
    label: str
    statement: str
    instant: bool
    elements: tuple[str, ...]
    nonnegative: bool = False
    partner: str | None = None
    partner_fallback: str | None = None
    tested: bool = True
    synonyms: tuple[str, ...] = ()


ITEMS: tuple[Item, ...] = (
    Item(
        "assets",
        "total assets",
        "balance_sheet",
        True,
        ("Assets",),
        True,
        "liabilities_and_equity",
        synonyms=("assets",),
    ),
    Item(
        "assets_current",
        "current assets",
        "balance_sheet",
        True,
        ("AssetsCurrent",),
        True,
        "assets",
        synonyms=("total current assets",),
    ),
    Item(
        "liabilities",
        "total liabilities",
        "balance_sheet",
        True,
        ("Liabilities",),
        True,
        "assets",
        synonyms=("liabilities",),
    ),
    Item(
        "liabilities_current",
        "current liabilities",
        "balance_sheet",
        True,
        ("LiabilitiesCurrent",),
        True,
        "liabilities",
        "assets",
        synonyms=("total current liabilities",),
    ),
    Item(
        "equity",
        "stockholders' equity",
        "balance_sheet",
        True,
        (
            "StockholdersEquity",
            "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
        ),
        False,
        "assets",
        synonyms=(
            "stockholders equity",
            "shareholders' equity",
            "shareholders equity",
            "total equity",
            "equity",
        ),
    ),
    Item(
        "liabilities_and_equity",
        "total liabilities and stockholders' equity",
        "balance_sheet",
        True,
        ("LiabilitiesAndStockholdersEquity",),
        True,
        "assets",
        synonyms=(
            "liabilities and equity",
            "liabilities and stockholders' equity",
            "liabilities and stockholders equity",
            "total liabilities and equity",
            "total liabilities and shareholders' equity",
        ),
    ),
    Item(
        "cash",
        "cash and cash equivalents",
        "balance_sheet",
        True,
        (
            "CashAndCashEquivalentsAtCarryingValue",
            "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
        ),
        True,
        "assets_current",
        "assets",
        synonyms=("cash", "cash equivalents"),
    ),
    Item(
        "revenue",
        "revenue",
        "income_statement",
        False,
        (
            "Revenues",
            "RevenueFromContractWithCustomerExcludingAssessedTax",
            "SalesRevenueNet",
            "RevenueFromContractWithCustomerIncludingAssessedTax",
        ),
        True,
        "assets",
        synonyms=("revenues", "total revenue", "total revenues", "net sales", "sales"),
    ),
    Item(
        "cost_of_revenue",
        "cost of revenue",
        "income_statement",
        False,
        ("CostOfRevenue", "CostOfGoodsAndServicesSold", "CostOfGoodsSold"),
        True,
        "revenue",
        synonyms=("cost of sales", "cost of goods sold", "cost of goods and services sold"),
    ),
    Item(
        "gross_profit",
        "gross profit",
        "income_statement",
        False,
        ("GrossProfit",),
        False,
        "revenue",
        synonyms=("gross margin",),
    ),
    Item(
        "operating_income",
        "operating income",
        "income_statement",
        False,
        ("OperatingIncomeLoss",),
        False,
        "revenue",
        synonyms=("operating income (loss)", "operating loss", "income from operations"),
    ),
    Item(
        "income_tax",
        "income tax expense",
        "income_statement",
        False,
        ("IncomeTaxExpenseBenefit",),
        False,
        "revenue",
        synonyms=("income tax", "income taxes", "provision for income taxes", "tax expense"),
    ),
    Item(
        "net_income",
        "net income",
        "income_statement",
        False,
        ("NetIncomeLoss", "ProfitLoss"),
        False,
        "revenue",
        synonyms=("net income (loss)", "net loss", "net earnings"),
    ),
    Item(
        "cfo",
        "net cash from operating activities",
        "cash_flow",
        False,
        ("NetCashProvidedByUsedInOperatingActivities",),
        False,
        "revenue",
        synonyms=(
            "operating cash flow",
            "cash from operations",
            "net cash provided by operating activities",
            "net cash provided by (used in) operating activities",
            "cash flows from operating activities",
            "operating activities",
        ),
    ),
    Item(
        "cfi",
        "net cash from investing activities",
        "cash_flow",
        False,
        ("NetCashProvidedByUsedInInvestingActivities",),
        False,
        "revenue",
        synonyms=(
            "investing cash flow",
            "net cash used in investing activities",
            "net cash provided by (used in) investing activities",
            "cash flows from investing activities",
            "investing activities",
        ),
    ),
    Item(
        "cff",
        "net cash from financing activities",
        "cash_flow",
        False,
        ("NetCashProvidedByUsedInFinancingActivities",),
        False,
        "revenue",
        synonyms=(
            "financing cash flow",
            "net cash used in financing activities",
            "net cash provided by (used in) financing activities",
            "cash flows from financing activities",
            "financing activities",
        ),
    ),
    Item(
        "cash_change",
        "net change in cash",
        "cash_flow",
        False,
        (
            "CashAndCashEquivalentsPeriodIncreaseDecrease",
            "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"
            "PeriodIncreaseDecreaseIncludingExchangeRateEffect",
        ),
        False,
        "cashflow_sum",
        synonyms=(
            "change in cash",
            "net increase in cash",
            "net decrease in cash",
            "net increase (decrease) in cash",
            "increase in cash",
            "decrease in cash",
        ),
    ),
    Item(
        "fx_effect",
        "effect of exchange rates on cash",
        "cash_flow",
        False,
        (
            "EffectOfExchangeRateOnCashAndCashEquivalents",
            "EffectOfExchangeRateOnCashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
        ),
        False,
        None,
        tested=False,
        synonyms=("exchange rate effect", "effect of exchange rate"),
    ),
    Item(
        "dda",
        "depreciation and amortisation",
        "cash_flow",
        False,
        ("DepreciationDepletionAndAmortization", "DepreciationAndAmortization", "Depreciation"),
        True,
        "assets",
        synonyms=(
            "depreciation and amortization",
            "depreciation",
            "depreciation, depletion and amortization",
        ),
    ),
    Item(
        "capex",
        "capital expenditure",
        "cash_flow",
        False,
        ("PaymentsToAcquirePropertyPlantAndEquipment",),
        True,
        "assets",
        synonyms=(
            "capital expenditures",
            "purchases of property, plant and equipment",
            "payments to acquire property, plant and equipment",
            "purchases of property and equipment",
        ),
    ),
)
ITEM_BY_KEY: dict[str, Item] = {item.key: item for item in ITEMS}
TESTED_KEYS: tuple[str, ...] = tuple(item.key for item in ITEMS if item.tested)
ALL_ELEMENTS: tuple[str, ...] = tuple(e for item in ITEMS for e in item.elements)

ORIGINAL_FORMS = ("10-K", "10-Q")
AMENDED_FORMS = ("10-K/A", "10-Q/A")
MAX_DURATION_DAYS = 380

RULE_LABELS: dict[str, str] = {
    "R1": "total assets equal total liabilities and stockholders' equity",
    "R2": "current assets do not exceed total assets",
    "R3": "current liabilities do not exceed total liabilities",
    "R4": "cash does not exceed current assets",
    "R5": "a value that must be non-negative is non-negative",
    "R6": "gross profit equals revenue minus cost of revenue",
    "R7": "the three cash flows and the exchange rate effect sum to the change in cash",
}
