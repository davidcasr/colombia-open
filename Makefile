.PHONY: bootstrap doctor extract build verify test lint format format-check typecheck audit sec check refresh clean

VENV := .venv
PYTHON := $(VENV)/Scripts/python.exe

bootstrap:
	uv venv --python 3.11 $(VENV)
	uv pip install -e ".[pipeline,dev,mcp]" -p $(VENV)
	$(PYTHON) -m pre_commit install

doctor:
	$(PYTHON) -m pip check
	$(PYTHON) scripts/check_validation_registration.py

extract:
	$(PYTHON) -m src.extractors.divipola_extractor

build:
	$(PYTHON) -m src.build_pipeline

verify:
	$(PYTHON) scripts/verify_pipeline.py

test:
	$(PYTHON) -m pytest

lint:
	$(PYTHON) -m ruff check src/ tests/

format:
	$(PYTHON) -m ruff format src/ tests/

format-check:
	$(PYTHON) -m ruff format --check src/ tests/

typecheck:
	$(PYTHON) -m mypy

audit:
	$(PYTHON) -m pip_audit

sec:
	$(PYTHON) -m bandit -c pyproject.toml -r src/

check: build verify test lint format-check typecheck sec

refresh: extract build verify test lint format-check typecheck audit sec

clean:
	rm -rf $(VENV) build dist *.egg-info .pytest_cache .mypy_cache .ruff_cache
