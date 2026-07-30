.PHONY: help install test lint typecheck fmt verify clean

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  %-14s %s\n", $$1, $$2}'

install:  ## editable install with dev extras
	pip install -e ".[dev]"

test:  ## unit tests (no GPU, no Isaac Sim)
	python -m pytest -q

test-upstream:  ## + the reference-loader compatibility proof
	NAVFM_UPSTREAM=third_party/visualnav-transformer python -m pytest -q

lint:  ## ruff
	ruff check src tests scripts

fmt:  ## ruff format
	ruff format src tests scripts

typecheck:  ## mypy
	mypy

verify: lint typecheck test  ## everything CI runs

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache build dist *.egg-info
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
