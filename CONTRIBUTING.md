# Contributing

Thank you for taking the time. The repository is a research artefact with a
pre-specified analysis plan, so contributions fall into two kinds.

## Code and documentation fixes

Bug fixes, clearer documentation, better tests and portability fixes are
welcome at any time.

1. Fork and create a branch from `main`.
2. Install in a fresh environment: `pip install -e ".[dev]"` and
   `pre-commit install`.
3. Make the change with type hints and a docstring on every public function.
4. Run `make check` (ruff, mypy, tests with coverage). All three must pass.
5. If the change touches a numbered requirement in
   `docs/validation/requirements.md`, update the traceability matrix by
   marking the test with `@pytest.mark.req("REQ-xxx")` and regenerating it
   with `make validation`.
6. Add a line to `CHANGELOG.md` under *Unreleased*.
7. Open a pull request. CI runs the tests on Linux and the quick pipeline from
   a clean environment.

## Changes to the analysis

Anything that changes what is flagged, how p-values are calibrated, how errors
are injected, how the split is drawn or what is reported is a change to the
analysis. Such a change is welcome, but it must be recorded under
*Deviations* in `docs/analysis_plan.md` with the reason, and the results must
be regenerated with `make all` so that the committed tables, figures and
notebook match the code.

## Style

- Python 3.11 or later, formatted and linted by ruff, type checked by mypy in
  strict mode.
- Plain lowercase commit messages that say what changed and why when the why
  is not obvious.
- Comments explain decisions, not syntax.
- No data from SEC EDGAR is committed. The manifest of retrieval dates and
  checksums is.

## Reporting a security issue

See `SECURITY.md`.
