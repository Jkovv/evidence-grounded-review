# Requirements

Numbered requirements for the review pipeline, written in the form a validated
system's specification would use. This repository is a research artefact and
is not a validated system; the package shows what the artefacts look like when
they are produced by the pipeline itself. Each requirement is linked to tests
in `traceability_matrix.md`, and the last test run is in `test_report.md`.
Risk is the consequence of the requirement failing unnoticed: high when a flag
or statement could mislead a reviewer, medium when a result could be wrong but
visibly so, low otherwise.

## Detection

| ID | Title | Statement | Risk |
|---|---|---|---|
| REQ-001 | Determinism | Identical input cells, injection and settings produce byte-identical flags and evidence files, across runs and across machines. | high |
| REQ-002 | Accounting identities | Rules R1 to R7 of the analysis plan fire exactly when the stated identity is violated beyond its tolerance, and flag every cell that enters the identity. | high |
| REQ-003 | Causal plausibility score | The score of a cell depends only on earlier periods of the same company and on the other items of the same period; a change to a later period does not change it. | high |
| REQ-004 | Conformal p-values and Benjamini-Hochberg | The p-value equals (1 + calibration scores at least as large) over (calibration size + 1); rejections match an exact rational implementation of the step-up procedure. | high |
| REQ-005 | Held-out testing | Only held-out companies are tested, and the calibration set is built from development companies alone. | high |

## Evidence and text

| ID | Title | Statement | Risk |
|---|---|---|---|
| REQ-006 | Evidence record schema | Every evidence record validates against the shipped JSON schema, lists only the source values that entered the decision, and carries accession number, form, filing date and retrieval date for each. | high |
| REQ-007 | Every flag has evidence | Every cell within the largest budget of any ranking and every Benjamini-Hochberg rejection has at least one evidence record. | high |
| REQ-008 | Template faithfulness | The template text passes the checker, including the strict exact-match pass, for every record. | medium |
| REQ-009 | Numbers are checked | A sentence with a number that is not in the evidence record, exactly or rounded with a stated unit, is rejected; percentages are never accepted. | high |
| REQ-010 | Line items are checked | A sentence naming a line item that is not in the evidence record is rejected. | high |
| REQ-011 | Periods are checked | A sentence with a date or period that is not in the evidence record is rejected. | high |
| REQ-012 | Fallback to the template | A rejected language-model text is replaced by the template and the rejection is logged with its reasons. | high |
| REQ-013 | The model never decides what to flag | Text is generated only for flags already produced by the deterministic core, and the model receives nothing but the evidence record (or, in the ablation, the raw table) and a writing instruction. | high |

## Audit trail and data

| ID | Title | Statement | Risk |
|---|---|---|---|
| REQ-014 | Tamper-evident log | The audit log is a hash chain; editing, deleting, inserting, swapping or truncating entries, and editing with a recomputed hash, are all detected by the verifier. | high |
| REQ-015 | Run context recorded | Every run start records the package version, Python version, platform, git commit, data manifest hash, split hash and all parameters. | medium |
| REQ-016 | SEC access policy | Every request to the SEC declares the user agent and requests are spaced at least the configured interval apart. | medium |
| REQ-017 | Pinned data | Every downloaded file is recorded with URL, retrieval date and SHA-256, and a changed or missing file is reported by the check command. | medium |
| REQ-018 | Split before analysis | The filing of record is the earliest original filing for a period, and the development and held-out split is a fixed-seed function of the company list alone. | high |
| REQ-019 | Injection as specified | Injected errors follow the five types and equal shares of the analysis plan, hit no cell twice, and swaps stay within a split. | medium |
| REQ-020 | Paired bootstrap | Bootstrap intervals use the same company resamples for every detector, and the unweighted resample reproduces the direct count. | medium |
