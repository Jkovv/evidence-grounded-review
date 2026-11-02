"""Language model backends that write query text from an evidence record.

The model only ever sees the prompt built here. It is never asked whether
anything should be flagged. Two backends: the Anthropic API and any server
with an OpenAI-compatible chat completions endpoint (for example Ollama with a
local open model).
"""

from __future__ import annotations

import hashlib
import json
import re
import urllib.request
from dataclasses import dataclass
from typing import Any, Protocol

from egr import config
from egr.evidence import Evidence, canonical

SYSTEM_PROMPT = (
    "You draft comment letters from the staff of a securities regulator to a company about one "
    "item in one of its filings. You are given an evidence record as JSON. Write at most three "
    "sentences of plain prose in the style of such a letter: refer to the filing by form, "
    "accession number and period, state what was observed, and ask the company to explain or "
    "revise. Use only the values, line items, dates and accession numbers that appear in the "
    "record; do not introduce any other number, name, period or line item; do not say what the "
    "correct value should be; do not speculate about causes. Write amounts in US dollars in "
    "full with thousands separators and dates as Month Day, Year. Output the letter text only."
)
RAW_SYSTEM_PROMPT = (
    "You draft comment letters from the staff of a securities regulator to a company about one "
    "item in one of its filings. You are given the company's reported figures for the flagged "
    "period and the four periods before it, and told which item and period were flagged and "
    "why. Write at most three sentences of plain prose in the style of such a letter: refer to "
    "the filing by form, accession number and period, state what was observed, and ask the "
    "company to explain or revise. Do not say what the correct value should be. Write amounts "
    "in US dollars in full with thousands separators and dates as Month Day, Year. Output the "
    "letter text only."
)
THINK_BLOCK = re.compile(r"<think>.*?</think>\s*", re.DOTALL)


@dataclass
class Generation:
    """What a backend returned, kept whole for the audit log."""

    text: str
    model: str
    backend: str
    prompt_hash: str
    raw: str
    error: str = ""


class Backend(Protocol):
    """A text generator."""

    name: str
    model: str

    def generate(self, system: str, user: str) -> Generation:
        """Return the model's text for a system prompt and a user message."""
        ...


def prompt_hash(system: str, user: str) -> str:
    """SHA-256 over the two prompt parts."""
    return hashlib.sha256((system + "\n\u0000\n" + user).encode("utf-8")).hexdigest()


class AnthropicBackend:
    """The Anthropic API through the official SDK."""

    name = "anthropic"

    def __init__(self, model: str = "") -> None:
        import anthropic

        self.model = model or "claude-sonnet-5-5"
        self._client = anthropic.Anthropic()

    def generate(self, system: str, user: str) -> Generation:
        """One non-streaming request; a refusal or an error gives an empty text."""
        h = prompt_hash(system, user)
        try:
            response = self._client.messages.create(
                model=self.model,
                max_tokens=config.LLM_MAX_TOKENS,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
        except Exception as e:
            return Generation("", self.model, self.name, h, "", f"{type(e).__name__}: {e}")
        raw = response.model_dump_json()
        if response.stop_reason == "refusal":
            return Generation("", self.model, self.name, h, raw, "refusal")
        text = "".join(block.text for block in response.content if block.type == "text")
        return Generation(text.strip(), self.model, self.name, h, raw)


class OpenAICompatibleBackend:
    """Any server with a /chat/completions endpoint, such as Ollama."""

    name = "openai_compatible"

    def __init__(self, model: str = "", base_url: str = config.LLM_BASE_URL) -> None:
        self.model = model or "qwen3:8b"
        self.base_url = base_url.rstrip("/")

    def generate(self, system: str, user: str) -> Generation:
        """One request with temperature 0; thinking is switched off for qwen3 models."""
        h = prompt_hash(system, user)
        body: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": 0,
            "max_tokens": config.LLM_MAX_TOKENS,
            "stream": False,
        }
        if self.model.startswith("qwen3"):
            body["messages"][-1]["content"] += " /no_think"
        req = urllib.request.Request(
            self.base_url + "/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=600) as r:
                raw = r.read().decode("utf-8")
        except Exception as e:
            return Generation("", self.model, self.name, h, "", f"{type(e).__name__}: {e}")
        try:
            text = json.loads(raw)["choices"][0]["message"]["content"]
        except (KeyError, IndexError, json.JSONDecodeError) as e:
            return Generation("", self.model, self.name, h, raw, f"unexpected response: {e}")
        return Generation(THINK_BLOCK.sub("", text).strip(), self.model, self.name, h, raw)


class OllamaBackend:
    """A local open model served by Ollama, through its native chat endpoint.

    The native endpoint is used because it can switch a model's thinking mode
    off, which the OpenAI-compatible endpoint of the same server cannot.
    """

    name = "ollama"

    def __init__(self, model: str = "", base_url: str = config.LLM_BASE_URL) -> None:
        self.model = model or "qwen3:4b"
        self.base_url = base_url.rstrip("/").removesuffix("/v1")

    def generate(self, system: str, user: str) -> Generation:
        """One request with temperature 0 and thinking off."""
        h = prompt_hash(system, user)
        body: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "options": {
                "temperature": 0,
                "num_predict": config.LLM_MAX_TOKENS,
                "seed": config.SEED,
            },
            "think": False,
            "stream": False,
        }
        req = urllib.request.Request(
            self.base_url + "/api/chat",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=900) as r:
                raw = r.read().decode("utf-8")
        except Exception as e:
            return Generation("", self.model, self.name, h, "", f"{type(e).__name__}: {e}")
        try:
            text = json.loads(raw)["message"]["content"]
        except (KeyError, json.JSONDecodeError) as e:
            return Generation("", self.model, self.name, h, raw, f"unexpected response: {e}")
        return Generation(THINK_BLOCK.sub("", text).strip(), self.model, self.name, h, raw)


def make_backend(kind: str = config.LLM_BACKEND, model: str = config.LLM_MODEL) -> Backend | None:
    """The configured backend (anthropic, openai_compatible or ollama), or None."""
    if kind == "anthropic":
        return AnthropicBackend(model)
    if kind == "openai_compatible":
        return OpenAICompatibleBackend(model)
    if kind == "ollama":
        return OllamaBackend(model)
    return None


def evidence_prompt(record: Evidence) -> tuple[str, str]:
    """System and user prompt for the evidence-record variant."""
    return SYSTEM_PROMPT, "Evidence record:\n" + canonical(record)


def raw_prompt(record: Evidence, raw_table: list[dict[str, Any]]) -> tuple[str, str]:
    """System and user prompt for the ablation that sees raw data instead of the record."""
    first = record["flagged_cell_ids"][0].split("|")
    reason = (
        f"identity rule {record['rule']} ({record['rule_statement']})"
        if record["detector"] == "rule"
        else "the value does not fit the company's earlier filings and the other items of "
        "the period"
    )
    lines = [
        f"Company: {record['company']['name']} (CIK {record['company']['cik']})",
        f"Flagged item: {config.ITEM_BY_KEY[first[2]].label} at the period ended {first[1]}",
        f"Reason: {reason}",
        "",
        "Reported figures (USD), one block per period:",
    ]
    for block in raw_table:
        lines.append(
            f"- period ended {block['period_end']}, Form {block['form']}, accession number "
            f"{block['accession_number']}, filed {block['filed']}:"
        )
        for item_key, value in block["values"].items():
            lines.append(f"    {config.ITEM_BY_KEY[item_key].label}: {value:,.0f}")
    return RAW_SYSTEM_PROMPT, "\n".join(lines)
