# Service image: the survey_etl API served by uvicorn, plus the
# survey-client command that turns survey CSV files into batch JSON.
#
# Base images are pinned by tag and digest. Update both together; read
# the digest with: docker buildx imagetools inspect <image>:<tag>
ARG PYTHON_IMAGE=python:3.14.10-slim-trixie@sha256:9aaa474097d094040649f2162a627c0049b408f52138d980916788d80f04802f
ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.13.9@sha256:d3b601f0c7b118bc1753febf7c41cc80981df678445e0254284eecf84db79a7d


# ---- uv: only its binary is used ----
FROM ${UV_IMAGE} AS uv


# ---- dependencies: the locked runtime dependencies in a venv ----
FROM ${PYTHON_IMAGE} AS dependencies

COPY --from=uv /uv /usr/local/bin/uv

# UV_COMPILE_BYTECODE: compile .pyc files now for a faster start.
# UV_LINK_MODE=copy: the cache is a separate mount; hard links fail.
# UV_PYTHON_DOWNLOADS=never: use the image's Python, never fetch one.
# UV_PROJECT_ENVIRONMENT: the venv path the runtime stage copies.
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv

WORKDIR /src

# Only pyproject.toml and uv.lock are read, so this stage is rebuilt
# only when they change, not when the source code does.
# --no-default-groups: no dev or notebook tools in the image.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    uv sync --locked --no-default-groups --no-install-project


# ---- project: the survey_etl and survey_client packages added ----
FROM dependencies AS project

COPY pyproject.toml uv.lock README.md ./
COPY src ./src

# --no-editable: install a copy of the project, not a link to /src,
# which the runtime stage does not have.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-default-groups --no-editable


# ---- runtime: the venv on a clean base, run as an unprivileged user ----
FROM ${PYTHON_IMAGE} AS runtime

# Fixed IDs keep the ownership of the database volume predictable.
RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --home-dir /app \
        --no-create-home app \
    && mkdir --parents /app/var \
    && chown app:app /app/var

COPY --from=project /opt/venv /opt/venv

ENV PATH="/opt/venv/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
# Numeric, so runtimes can check it is not root without /etc/passwd.
USER 10001:10001

# The default database URLs (sqlite:///var/<environment>.db) are
# relative to /app, so both environments keep their file here.
VOLUME ["/app/var"]
EXPOSE 8000

# The slim image has no curl; the standard library does the request.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)"]

# APP_ENV has no default on purpose: a container started without it
# stops with an error instead of guessing the environment.
# --host 0.0.0.0: listen on the container's interface, not only on
# its own loopback, so the published port reaches it.
CMD ["uvicorn", "survey_etl.api.asgi:create_application", "--factory", \
     "--host", "0.0.0.0", "--port", "8000"]
