# Reproduce everything from scratch:  make all
# Short run on 24 companies with 2 replicates, written to results-quick/:  make all-quick
# Set EGR_DATA_DIR to keep the raw SEC files outside the repository.
# Set EGR_LLM_BACKEND (anthropic or openai_compatible) and EGR_LLM_MODEL to run
# the language-model variants of the query text; without them the template runs alone.
PYTHON ?= python
export PYTHONPATH := src

.PHONY: all all-quick install data prepare detect determinism texts verify-log evaluate figures notebook notebook-quick check lint type test validation clean clean-quick

all: data prepare detect determinism texts evaluate verify-log figures notebook validation

all-quick:
	EGR_QUICK=1 $(MAKE) data prepare detect determinism texts evaluate verify-log figures notebook-quick

install:
	$(PYTHON) -m pip install -e ".[dev,anthropic]"
	pre-commit install

data:
	$(PYTHON) data/download_sec.py $(if $(EGR_QUICK),--quick)

prepare:
	$(PYTHON) -m egr.cli prepare

detect:
	$(PYTHON) -m egr.cli detect

determinism:
	$(PYTHON) -m egr.cli determinism $(if $(EXPECT),--expect $(EXPECT))

texts:
	$(PYTHON) -m egr.cli texts

verify-log:
	$(PYTHON) -m egr.cli verify-log --tamper

evaluate:
	$(PYTHON) -m egr.cli evaluate

figures:
	$(PYTHON) -m egr.cli figures

notebook:
	$(PYTHON) -m jupyter nbconvert --to notebook --execute --inplace notebooks/walkthrough.ipynb

# the executed copy goes next to the quick results, the committed notebook is left alone
notebook-quick:
	EGR_QUICK=1 $(PYTHON) -m jupyter nbconvert --to notebook --execute notebooks/walkthrough.ipynb --output-dir results-quick --output walkthrough

check: lint type test

lint:
	$(PYTHON) -m ruff check src tests scripts data
	$(PYTHON) -m ruff format --check src tests scripts data

type:
	$(PYTHON) -m mypy src scripts data

test:
	$(PYTHON) -m pytest --cov=egr --cov-report=term-missing --cov-report=xml --junitxml=results/test-report.xml

validation:
	$(PYTHON) scripts/validation_report.py

clean-quick:
	$(PYTHON) -m egr.cli clean-quick

clean: clean-quick
	rm -rf data/processed results/cells results/audit results/tables/*.csv results/figures/*.png results/summary.json results/text_examples.md
