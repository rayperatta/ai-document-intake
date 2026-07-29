.PHONY: help install dev test lint format run-api clean

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}; {printf "\033[36m%-16s\033[0m %s\n", $$1, $$2}'

install:  ## Install production deps
	pip install -e .

dev:  ## Install dev deps (editable + test/lint tools)
	pip install -e ".[dev]"

test:  ## Run pytest
	pytest

lint:  ## Run ruff
	ruff check .

format:  ## Auto-format with ruff
	ruff check --fix .

run-api:  ## Start FastAPI dev server
	uvicorn docintake.api.app:app --reload --host 0.0.0.0 --port 8000

clean:  ## Remove caches and build artifacts
	rm -rf build dist *.egg-info .pytest_cache .ruff_cache __pycache__
	find . -type d -name __pycache__ -exec rm -rf {} +
