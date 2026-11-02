"""The whole command line pipeline on synthetic data, without network or SEC files."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd
import pytest

from egr import cli, config
from egr.cells import Companies, all_cells


def write_processed(companies: Companies, out: Path) -> None:
    rows = []
    for c in all_cells(companies):
        rows.append(
            {
                "cik": c.cik,
                "name": c.name,
                "period_end": c.period_end,
                "period_start": c.period_start,
                "ytd_months": c.ytd_months,
                "item": c.item,
                "element": c.source.element,
                "value": c.value,
                "accn": c.source.accn,
                "form": c.source.form,
                "filed": c.source.filed,
                "amended_changed": c.cik == 1011
                and c.item == "net_income"
                and c.period_end.endswith("12-31"),
                "amended_value": float("nan"),
                "amended_accn": "",
                "amended_filed": "",
                "revised_later": False,
                "split": c.split,
            }
        )
    out.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(out / "cells.parquet", index=False)
    pd.DataFrame(
        [
            {
                "cik": k,
                "name": v.name,
                "n_periods": len(v.periods),
                "elements": "{}",
                "split": v.split,
            }
            for k, v in companies.items()
        ]
    ).to_parquet(out / "companies.parquet", index=False)
    pd.DataFrame([{"cik": 1010, "filing_date": "2015-02-01"}]).to_parquet(
        out / "nonreliance.parquet", index=False
    )
    (out / "prepare_summary.json").write_text(
        json.dumps({"companies_kept": len(companies)}), encoding="utf-8"
    )


@pytest.fixture
def pipeline_dirs(tmp_path: Path, companies: Companies, monkeypatch):
    processed = tmp_path / "processed"
    results = tmp_path / "results"
    write_processed(companies, processed)
    monkeypatch.setattr(config, "PROCESSED_DIR", processed)
    monkeypatch.setattr(config, "RESULTS_DIR", results)
    monkeypatch.setattr(config, "TABLES_DIR", results / "tables")
    monkeypatch.setattr(config, "FIGURES_DIR", results / "figures")
    monkeypatch.setattr(config, "CELLS_DIR", results / "cells")
    monkeypatch.setattr(config, "AUDIT_DIR", results / "audit")
    monkeypatch.setattr(config, "MANIFEST_PATH", tmp_path / "missing-manifest.json")
    monkeypatch.setattr(config, "N_REPLICATES", 1)
    monkeypatch.setattr(config, "N_BOOTSTRAP", 15)
    monkeypatch.setattr(config, "N_TEXT_FLAGS", 4)
    monkeypatch.setattr(cli, "LOG_PATH", results / "audit" / "audit.jsonl")
    return results


@pytest.mark.req("REQ-001")
def test_cli_pipeline_end_to_end(pipeline_dirs: Path):
    results = pipeline_dirs
    assert cli.main(["detect"]) == 0
    stems = {p.name.rsplit("_", 1)[0] for p in (results / "cells").glob("*_cells.parquet")}
    assert stems == {
        "clean_r00",
        "primary_r00",
        "sens0.005_r00",
        "sens0.02_r00",
        "primary-injectedcal_r00",
    }
    assert cli.main(["determinism", "--reset"]) == 0
    det = pd.read_csv(results / "tables" / "determinism.csv")
    assert bool(det["two_runs_identical"].iloc[0])
    assert cli.main(["determinism", "--expect", det["flags_sha256"].iloc[0]]) == 0
    assert cli.main(["determinism", "--expect", "0" * 64]) == 1
    assert cli.main(["texts"]) == 0
    faith = pd.read_csv(results / "tables" / "faithfulness.csv")
    assert faith.loc[faith["variant"] == "template", "rejection_rate"].iloc[0] == 0.0
    assert cli.main(["evaluate"]) == 0
    for name in (
        "budget_metrics",
        "recall_by_type",
        "budget_differences",
        "false_flag_rate",
        "amendments",
        "non_reliance",
        "runtime",
        "injection_shortfall",
    ):
        assert (results / "tables" / f"{name}.csv").exists(), name
    summary = json.loads((results / "summary.json").read_text(encoding="utf-8"))
    assert "primary" in summary and "false_flag_rate" in summary
    assert cli.main(["verify-log", "--tamper"]) == 0
    tamper = pd.read_csv(results / "tables" / "audit_tamper.csv")
    assert tamper["detected"].iloc[:-1].all() and not tamper["detected"].iloc[-1]
    assert cli.main(["figures"]) == 0
    assert (results / "figures" / "budget_comparison.png").exists()
    assert (results / "figures" / "false_flag_rate_dark.png").exists()
    log_lines = (results / "audit" / "audit.jsonl").read_text(encoding="utf-8").splitlines()
    types = [json.loads(line)["type"] for line in log_lines]
    assert (
        types[0] == "run_start" and "flag" in types and "run_end" in types and "evaluate" in types
    )
    assert cli.cmd_clean_quick(argparse.Namespace()) == 0
