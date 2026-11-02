# Changelog

All notable changes to this project are recorded here. The format follows
Keep a Changelog and the project uses semantic versioning.

## [0.1.0] - 2026-11-02

### Added

- literature and standards check with verified citations and the
  pre-specified analysis plan
- SEC EDGAR download script with rate limiting, declared user agent and a
  checksum manifest
- as-reported cell tables for twenty line items, amendment labels from
  10-K/A and 10-Q/A filings, 8-K Item 4.02 dates, and a fixed-seed split
- error injection: sign flips, scale slips, digit transpositions,
  copy-forwards and cross-company swaps at documented rates
- identity rules R1 to R7 and a causal plausibility score in pure Python
  arithmetic
- conformal p-values with Benjamini-Hochberg in integer arithmetic
- schema-validated evidence records and an append-only hash-chained audit
  log with a verifier and tampering cases
- template and language-model query text with a faithfulness checker and
  template fallback
- held-out evaluation with a paired company bootstrap, figures, an executed
  walkthrough notebook and a short methods paper
- validation package: numbered requirements, traceability matrix and test
  report generated from the tests, known limitations
- CI: lint, type check, tests with coverage on Python 3.11 and 3.13, the
  quick pipeline from a clean environment and a cross-runner determinism
  check
