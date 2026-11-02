#!/usr/bin/env bash
# Same steps as `make all`, for machines without make (on Windows, run it from
# Git Bash or WSL).
#
#   ./reproduce.sh            full run, writes results/ and re-executes the notebook
#   ./reproduce.sh --quick    same as `make all-quick`, writes results-quick/
#
# PYTHON can be set as for make. EGR_LLM_BACKEND and EGR_LLM_MODEL select the
# language model for the query text; without them only the template runs.
set -euo pipefail
cd "$(dirname "$0")"

PYTHON=${PYTHON:-python}
export PYTHONPATH=src

case "${1:-}" in
    "")      notebook=(--inplace); data_flag=() ;;
    --quick) export EGR_QUICK=1
             notebook=(--output-dir results-quick --output walkthrough); data_flag=(--quick) ;;
    *)       echo "usage: $0 [--quick]" >&2; exit 2 ;;
esac

run() {
    echo ">> $*"
    "$@"
}

run "$PYTHON" data/download_sec.py "${data_flag[@]}"
for step in prepare detect determinism texts evaluate; do
    run "$PYTHON" -m egr.cli "$step"
done
run "$PYTHON" -m egr.cli verify-log --tamper
run "$PYTHON" -m egr.cli figures
run "$PYTHON" -m jupyter nbconvert --to notebook --execute "${notebook[@]}" notebooks/walkthrough.ipynb
if [ -z "${EGR_QUICK:-}" ]; then
    run "$PYTHON" scripts/validation_report.py
fi
echo "done"
