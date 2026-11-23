SHELL := bash
.SHELLFLAGS := -euo pipefail -c
.DEFAULT_GOAL := help
MAKEFLAGS += --warn-undefined-variables --no-builtin-rules

# Service image and container settings; override on the command line,
# for example: make docker-run ENV=prod
IMAGE ?= etl-example:local
ENV ?= dev

.PHONY: help install lock format lint typecheck test test-integration \
	check run-dev docker-build docker-run docker-stop smoke-test

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

lint: ## Lint Python with ruff, the Dockerfile and the shell scripts.
	uv run ruff check
	uv run ruff format --check
	uv run hadolint Dockerfile
	uv run shellcheck scripts/*.sh

typecheck: ## Type-check with mypy --strict.
	uv run mypy

test: ## Run the test suite with coverage.
	uv run pytest

test-integration: ## Test the IMAGE in Docker containers (build it first).
	INTEGRATION_IMAGE="$(IMAGE)" uv run pytest -m integration --no-cov

check: lint typecheck test ## Run the checks of the CI check job.

# Use for writing or debugging code.
run-dev: ## Serve the API locally in dev, reloading on code changes.
	APP_ENV=dev uv run uvicorn survey_etl.api.asgi:create_application \
		--factory --reload

docker-build: ## Build the service image as IMAGE.
	docker build --tag "$(IMAGE)" .

docker-run: ## Start the ENV (dev or prod) container from IMAGE.
	scripts/run-container.sh "$(ENV)" "$(IMAGE)"

# `docker stop` sends SIGTERM and waits, so uvicorn finishes open requests
# and closes the database before the container is removed.
docker-stop: ## Stop the ENV container cleanly and remove it; its volume stays.
	docker stop "etl-example-$(ENV)"
	docker rm "etl-example-$(ENV)"

smoke-test: ## Start IMAGE as ENV and check /health and /docs, as CD does.
	scripts/smoke-test.sh "$(ENV)" "$(IMAGE)"
