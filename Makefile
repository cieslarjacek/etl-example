SHELL := bash
.SHELLFLAGS := -euo pipefail -c
.DEFAULT_GOAL := help
MAKEFLAGS += --warn-undefined-variables --no-builtin-rules

IMAGE ?= etl-example:local
CONTAINER ?= etl-example
HOST_PORT ?= 8000
BASE_URL ?= http://localhost:$(HOST_PORT)
# HTTP status /docs must return: 200 in dev, 404 in prod.
EXPECTED_DOCS_STATUS ?= 200

.PHONY: help install format lint typecheck test notebook notebook-outputs check \
	run-dev docker-build docker-run-dev docker-run-prod docker-stop demo \
	smoke-test

help: ## Show this help.
	@grep -E '^[a-z-]+:.*## ' "$(firstword $(MAKEFILE_LIST))" \
		| awk -F ':.*## ' '{printf "  %-16s %s\n", $$1, $$2}'

install: ## Install the project and dev tools from the lockfile.
	uv sync --locked

format: ## Format code and sort imports.
	uv run ruff check --select I --fix
	uv run ruff format

lint: ## Lint Python with ruff and shell scripts with shellcheck.
	uv run ruff check
	uv run ruff format --check
	shellcheck scripts/*.sh

typecheck: ## Type-check with mypy --strict.
	uv run mypy

test: ## Run the test suite with coverage.
	uv run pytest

notebook: ## Execute the example notebook end to end.
	uv run python scripts/run_notebook.py notebooks/example.ipynb

notebook-outputs: ## Execute the notebook and save its outputs in place.
	uv run python scripts/run_notebook.py notebooks/example.ipynb \
		--output notebooks/example.ipynb

check: lint typecheck test notebook ## Run every check CI runs.

run-dev: ## Serve the API locally in the dev environment.
	APP_ENV=dev uv run uvicorn etl_example.asgi:create_application \
		--factory --reload

docker-build: ## Build the Docker image as $(IMAGE).
	docker build --tag "$(IMAGE)" .

docker-run-dev: ## Run $(IMAGE) with APP_ENV=dev and wait until healthy.
	docker run --detach --rm --name "$(CONTAINER)" --env APP_ENV=dev \
		--publish "$(HOST_PORT):8000" "$(IMAGE)"
	scripts/wait-for-health.sh "$(BASE_URL)"

docker-run-prod: ## Run $(IMAGE) with APP_ENV=prod and wait until healthy.
	docker run --detach --rm --name "$(CONTAINER)" --env APP_ENV=prod \
		--publish "$(HOST_PORT):8000" "$(IMAGE)"
	scripts/wait-for-health.sh "$(BASE_URL)"

docker-stop: ## Stop the running container.
	docker stop "$(CONTAINER)"

demo: ## Load waves 1-3 into the running container and print summaries.
	scripts/demo.sh "$(BASE_URL)" "$(CONTAINER)"

smoke-test: ## Check /health and the /docs status of a running API.
	scripts/smoke-test.sh "$(BASE_URL)" "$(EXPECTED_DOCS_STATUS)"
