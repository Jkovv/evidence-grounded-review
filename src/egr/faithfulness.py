"""Faithfulness checker: every number, line item and period must be in the evidence.

A text is split into sentences. Each sentence passes only if every claim it
makes can be matched to the evidence record: numbers to source or computed
values (exactly, or rounded to the digits written, with thousand, million and
billion units applied), line item names to items in the record, dates and
years to the periods and filing dates in the record. A text with any failing
sentence is rejected.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

from egr import config
from egr.evidence import Evidence
from egr.querytext import MONTHS

UNIT_FACTORS = {
    "thousand": 1e3,
    "thousands": 1e3,
    "k": 1e3,
    "million": 1e6,
    "millions": 1e6,
    "mn": 1e6,
    "m": 1e6,
    "mm": 1e6,
    "billion": 1e9,
    "billions": 1e9,
    "bn": 1e9,
    "b": 1e9,
    "trillion": 1e12,
    "trillions": 1e12,
}
ACCESSION = re.compile(r"\b\d{10}-\d{2}-\d{6}\b")
ISO_DATE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
LONG_DATE = re.compile(
    r"\b("
    + "|".join(MONTHS)
    + r"|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\.?\s+(\d{1,2}),?\s+(\d{4})\b"
)
NUMBER = re.compile(
    r"(?<![\w.])-?\(?\$?\s?(\d{1,3}(?:,\d{3})+|\d+)(\.\d+)?\)?\s*"
    r"(thousands?|millions?|billions?|trillions?|percent|%|bn|mn|mm|k|m|b)?(?![\w])",
    re.IGNORECASE,
)
SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"'(])")
ABBREVIATIONS = (
    "Inc.",
    "Corp.",
    "Co.",
    "Ltd.",
    "No.",
    "Mr.",
    "Ms.",
    "vs.",
    "U.S.",
    "e.g.",
    "i.e.",
    "approx.",
)


@dataclass
class SentenceCheck:
    """Outcome for one sentence."""

    text: str
    claims: int = 0
    verified: int = 0
    failures: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Whether every claim was verified."""
        return not self.failures


@dataclass
class TextCheck:
    """Outcome for a whole text."""

    accepted: bool
    sentences: list[SentenceCheck]

    @property
    def claims(self) -> int:
        """Claims extracted over all sentences."""
        return sum(s.claims for s in self.sentences)

    @property
    def verified(self) -> int:
        """Claims verified over all sentences."""
        return sum(s.verified for s in self.sentences)

    @property
    def failures(self) -> list[str]:
        """All failure messages."""
        return [f for s in self.sentences for f in s.failures]


def split_sentences(text: str) -> list[str]:
    """Split on sentence ends, protecting common abbreviations."""
    protected = text
    for abbr in ABBREVIATIONS:
        protected = protected.replace(abbr, abbr.replace(".", "\u0000"))
    parts = SENTENCE_END.split(protected.strip())
    return [p.replace("\u0000", ".").strip() for p in parts if p.strip()]


def significant_digits(mantissa: str, decimals: str) -> int:
    """Significant digits of a written number, for example 1,230 -> 3, 4.50 -> 3."""
    digits = (mantissa.replace(",", "") + decimals.lstrip(".")).lstrip("0")
    if not decimals:
        digits = digits.rstrip("0")
    return max(1, len(digits))


def round_to(x: float, digits: int) -> float:
    """X rounded to a number of significant digits."""
    if x == 0:
        return 0.0
    return float(f"{x:.{digits}g}")


class Allowed:
    """The claims an evidence record licenses."""

    def __init__(self, record: Evidence, strict: bool = False) -> None:
        self.strict = strict
        self.numbers: list[float] = []
        self.dates: set[str] = set()
        self.years: set[int] = set()
        self.months: set[int] = set()
        self.accessions: set[str] = set()
        self.items: set[str] = set()
        for s in record["sources"]:
            self.numbers.append(abs(float(s["value"])))
            for key in ("period_start", "period_end", "filed"):
                if s[key]:
                    self.dates.add(str(s[key]))
                    self.years.add(int(str(s[key])[:4]))
            if s["ytd_months"]:
                self.months.add(int(s["ytd_months"]))
            self.accessions.add(str(s["accession_number"]))
            self.items.add(str(s["item"]))
        self.dates.add(str(record["period_end"]))
        self.years.add(int(str(record["period_end"])[:4]))
        for value in record["computed"].values():
            self.numbers.append(abs(float(value)))
        self.numbers = sorted(set(self.numbers))

    def number_ok(self, value: float, digits: int, unit: str) -> bool:
        """Whether a written number matches an allowed value."""
        if unit in ("percent", "%"):
            return False
        factor = UNIT_FACTORS.get(unit.lower(), 1.0) if unit else 1.0
        scaled = abs(value) * factor
        for x in self.numbers:
            if x == scaled:
                return True
            if self.strict:
                continue
            if round_to(x, digits) == scaled and digits >= 1:
                return True
            if x == 0 and scaled == 0:
                return True
        if not unit and float(value).is_integer():
            n = int(value)
            if n in self.years or n in self.months:
                return True
        return False


_PHRASES: list[tuple[str, str]] = sorted(
    [(item.label.lower(), item.key) for item in config.ITEMS]
    + [(syn.lower(), item.key) for item in config.ITEMS for syn in item.synonyms],
    key=lambda p: -len(p[0]),
)


def mentioned_items(sentence: str) -> list[tuple[str, str]]:
    """Line item phrases found in a sentence, longest match wins at each position."""
    lowered = sentence.lower().replace("\u2019", "'")
    taken: list[tuple[int, int]] = []
    found: list[tuple[str, str]] = []
    for phrase, key in _PHRASES:
        for m in re.finditer(r"(?<![\w'])" + re.escape(phrase) + r"(?![\w'])", lowered):
            if any(a <= m.start() and m.end() <= b for a, b in taken):
                continue
            taken.append((m.start(), m.end()))
            found.append((phrase, key))
    return found


def check_sentence(sentence: str, allowed: Allowed) -> SentenceCheck:
    """Verify every claim in one sentence."""
    result = SentenceCheck(sentence)
    rest = sentence
    for m in ACCESSION.finditer(rest):
        result.claims += 1
        if m.group(0) in allowed.accessions:
            result.verified += 1
        else:
            result.failures.append(f"accession number {m.group(0)} not in evidence")
    rest = ACCESSION.sub(" ", rest)
    for m in LONG_DATE.finditer(rest):
        month_name, day, year = m.group(1), int(m.group(2)), int(m.group(3))
        month = next(
            (
                i + 1
                for i, name in enumerate(MONTHS)
                if name.lower().startswith(month_name.lower()[:3])
            ),
            0,
        )
        result.claims += 1
        try:
            iso = date(year, month, day).isoformat()
        except ValueError:
            iso = ""
        if iso in allowed.dates:
            result.verified += 1
        else:
            result.failures.append(f"date {m.group(0)} not in evidence")
    rest = LONG_DATE.sub(" ", rest)
    for m in ISO_DATE.finditer(rest):
        result.claims += 1
        if m.group(0) in allowed.dates:
            result.verified += 1
        else:
            result.failures.append(f"date {m.group(0)} not in evidence")
    rest = ISO_DATE.sub(" ", rest)
    for phrase, key in mentioned_items(sentence):
        result.claims += 1
        if key in allowed.items:
            result.verified += 1
        else:
            result.failures.append(f"line item '{phrase}' not in evidence")
    for m in NUMBER.finditer(rest):
        mantissa, decimals, unit = m.group(1), m.group(2) or "", m.group(3) or ""
        value = float(mantissa.replace(",", "") + decimals)
        result.claims += 1
        if allowed.number_ok(value, significant_digits(mantissa, decimals), unit):
            result.verified += 1
        else:
            result.failures.append(f"number {m.group(0).strip()} not in evidence")
    return result


def check_text(text: str, record: Evidence, strict: bool = False) -> TextCheck:
    """Check a whole text against an evidence record."""
    allowed = Allowed(record, strict=strict)
    sentences = [check_sentence(s, allowed) for s in split_sentences(text)]
    if not sentences:
        return TextCheck(False, [SentenceCheck("", failures=["empty text"])])
    return TextCheck(all(s.ok for s in sentences), sentences)
