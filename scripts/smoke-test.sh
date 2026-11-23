#!/usr/bin/env bash
# Start an image as one environment and check that it answers.
#
# Usage: scripts/smoke-test.sh <dev|prod> <image>
#
# Checks GET /health (status ok, the right environment) and GET /docs
# (200 in dev, 404 in prod, where the API docs are switched off). The
# container and its anonymous volume are removed at the end; its log
# is printed when a check fails. SMOKE_PORT overrides the host port
# (default 8000).
set -euo pipefail

readonly CONTAINER_PORT=8000
readonly DEFAULT_HOST_PORT=8000
readonly START_TIMEOUT_SECONDS=60

usage() {
    echo "usage: $0 <dev|prod> <image>" >&2
    exit 2
}

fail() {
    echo "smoke test failed: $1" >&2
    docker logs "${CONTAINER_NAME}" >&2 || true
    exit 1
}

remove_container() {
    # --volumes: also remove the anonymous volume of /app/var.
    docker rm --force --volumes "${CONTAINER_NAME}" >/dev/null 2>&1 || true
}

wait_until_healthy() {
    local base_url="$1"
    local waited_seconds=0
    until curl --silent --fail --output /dev/null "${base_url}/health"; do
        if ((waited_seconds >= START_TIMEOUT_SECONDS)); then
            fail "no answer from ${base_url}/health in ${START_TIMEOUT_SECONDS} s"
        fi
        sleep 1
        waited_seconds=$((waited_seconds + 1))
    done
}

main() {
    if [[ $# -ne 2 ]]; then
        usage
    fi
    local environment="$1"
    local image="$2"
    local expected_docs_status
    case "${environment}" in
        dev) expected_docs_status=200 ;;
        prod) expected_docs_status=404 ;;
        *) usage ;;
    esac
    local base_url="http://127.0.0.1:${SMOKE_PORT:-${DEFAULT_HOST_PORT}}"

    CONTAINER_NAME="etl-example-smoke-${environment}"
    trap remove_container EXIT
    remove_container
    docker run --detach \
        --name "${CONTAINER_NAME}" \
        --env "APP_ENV=${environment}" \
        --publish "127.0.0.1:${SMOKE_PORT:-${DEFAULT_HOST_PORT}}:${CONTAINER_PORT}" \
        "${image}" >/dev/null

    wait_until_healthy "${base_url}"
    local health_body
    health_body="$(curl --silent --show-error "${base_url}/health")"
    local expected_health_body="{\"status\":\"ok\",\"environment\":\"${environment}\"}"
    if [[ "${health_body}" != "${expected_health_body}" ]]; then
        fail "/health answered ${health_body}, expected ${expected_health_body}"
    fi

    local docs_status
    docs_status="$(curl --silent --output /dev/null --write-out '%{http_code}' \
        "${base_url}/docs")"
    if [[ "${docs_status}" != "${expected_docs_status}" ]]; then
        fail "/docs answered ${docs_status}, expected ${expected_docs_status}"
    fi

    echo "smoke test passed: ${image} as ${environment}"
}

main "$@"
