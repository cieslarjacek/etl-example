SHELL := bash
.SHELLFLAGS := -euo pipefail -c
.DEFAULT_GOAL := help
MAKEFLAGS += --warn-undefined-variables --no-builtin-rules

.PHONY: help install lock format lint typecheck test check run-dev

help: ## Show this help.
	@grep -E '^[a-z-]+:.*## ' "$(firstword $(MAKEFILE_LIST))" \
		| awk -F ':.*## ' '{printf "  %-16s %s\n", $$1, $$2}'

install: ## Install the project and dev tools from the lockfile.
	uv sync --locked

lock: ## Re-resolve uv.lock after editing dependencies in pyproject.toml.
	uv lock

format: ## Format code and sort imports.
	uv run ruff check --select I --fix
	uv run ruff format

lint: ## Lint and check formatting with ruff.
	uv run ruff check
	uv run ruff format --check

typecheck: ## Type-check with mypy --strict.
	uv run mypy

test: ## Run the test suite with coverage.
	uv run pytest

check: lint typecheck test ## Run every check CI runs.

run-dev: ## Serve the API locally in dev, reloading on code changes.
	APP_ENV=dev uv run uvicorn survey_etl.api.asgi:create_application \
		--factory --reload
