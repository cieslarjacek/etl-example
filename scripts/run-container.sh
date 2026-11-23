#!/usr/bin/env bash
# Start the service container of one environment in the background.
#
# Usage: scripts/run-container.sh <dev|prod> [image]
#
# The container is named etl-example-<environment> and keeps its
# database in the named volume etl-example-<environment>. Set HOST_PORT
# to override the published port (dev 8000, prod 8001).
set -euo pipefail

readonly DEFAULT_IMAGE="etl-example:local"
readonly CONTAINER_PORT=8000
readonly DEV_HOST_PORT=8000
readonly PROD_HOST_PORT=8001

usage() {
    echo "usage: $0 <dev|prod> [image]" >&2
    exit 2
}

main() {
    if [[ $# -lt 1 || $# -gt 2 ]]; then
        usage
    fi
    local environment="$1"
    local image="${2:-${DEFAULT_IMAGE}}"
    local host_port
    case "${environment}" in
        dev) host_port="${HOST_PORT:-${DEV_HOST_PORT}}" ;;
        prod) host_port="${HOST_PORT:-${PROD_HOST_PORT}}" ;;
        *) usage ;;
    esac

    # Published on 127.0.0.1 only: the API has no authentication.
    docker run --detach \
        --name "etl-example-${environment}" \
        --env "APP_ENV=${environment}" \
        --publish "127.0.0.1:${host_port}:${CONTAINER_PORT}" \
        --volume "etl-example-${environment}:/app/var" \
        "${image}"
    echo "etl-example-${environment} serves http://localhost:${host_port}"
}

main "$@"
