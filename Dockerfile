# syntax=docker/dockerfile:1

# Base images, overridable at build time. Pin by digest by appending
# "@sha256:<digest>" (see README, "Pinning base images").
ARG PYTHON_IMAGE=python:3.15.2-slim-trixie
ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.13.8

FROM ${UV_IMAGE} AS uv

# ---- build: install the locked dependencies and the package ----
FROM ${PYTHON_IMAGE} AS builder
COPY --from=uv /uv /usr/local/bin/uv
# UV_COMPILE_BYTECODE: compile .pyc at build time for faster start-up.
# UV_LINK_MODE=copy: the cache is a separate mount, hard links fail.
# UV_PYTHON_DOWNLOADS=never: use the base image's Python only.
# UV_PROJECT_ENVIRONMENT: create the virtual environment in /opt/venv.
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /src
# Dependencies first: this layer stays cached until uv.lock changes.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project
COPY README.md ./
COPY src ./src
# --no-editable copies the package into the venv, so the runtime stage
# needs no source tree.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable

# ---- runtime: Python, the virtual environment and the sample data ----
FROM ${PYTHON_IMAGE} AS runtime
RUN useradd --system --uid 10001 --no-create-home app
WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY data ./data
# var/ holds the SQLite database and must be writable by the app user.
RUN mkdir var && chown app var
# PYTHONUNBUFFERED: send log lines to docker logs immediately.
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    APP_ENV=prod
USER app
EXPOSE 8000
# The slim image has no curl: probe /health with the standard library.
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"]
CMD ["uvicorn", "etl_example.asgi:create_application", "--factory", \
     "--host", "0.0.0.0", "--port", "8000"]
