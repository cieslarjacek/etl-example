#!/usr/bin/env bash
# Wait until the API answers GET /health, or fail after a timeout.
# Usage: scripts/wait-for-health.sh BASE_URL
set -euo pipefail

readonly MAX_ATTEMPTS=30
readonly RETRY_DELAY_SECONDS=1

main() {
  local base_url="${1:?usage: wait-for-health.sh BASE_URL}"
  local attempt
  for ((attempt = 1; attempt <= MAX_ATTEMPTS; attempt++)); do
    if curl --silent --fail --output /dev/null "${base_url}/health"; then
      echo "API is healthy at ${base_url}"
      return 0
    fi
    sleep "${RETRY_DELAY_SECONDS}"
  done
  echo "API at ${base_url} is not healthy after ${MAX_ATTEMPTS} attempts" >&2
  return 1
}

main "$@"
