#!/usr/bin/env bash
# Read-only smoke test of a deployed API: health, database and docs.
# It never writes, so it is safe to run against prod.
# Usage: scripts/smoke-test.sh BASE_URL EXPECTED_DOCS_STATUS
#   EXPECTED_DOCS_STATUS: 200 where docs are enabled (dev), 404 in prod.
set -euo pipefail

readonly USAGE="usage: smoke-test.sh BASE_URL EXPECTED_DOCS_STATUS"
# A wave summary request reaches the database: 200 if the wave is
# stored, 404 if not; anything else means the database is broken.
readonly PROBE_PATH="/waves/1/summary"

http_status() {
  curl --silent --output /dev/null --write-out "%{http_code}" "$1"
}

check_status() {
  local name="$1" url="$2" allowed_pattern="$3"
  local status
  status="$(http_status "${url}")"
  if [[ ! "${status}" =~ ^(${allowed_pattern})$ ]]; then
    echo "FAIL ${name}: ${url} returned ${status}," \
      "expected ${allowed_pattern}" >&2
    return 1
  fi
  echo "ok   ${name}: ${url} returned ${status}"
}

main() {
  local base_url="${1:?${USAGE}}"
  local expected_docs_status="${2:?${USAGE}}"
  check_status "health" "${base_url}/health" "200"
  check_status "database" "${base_url}${PROBE_PATH}" "200|404"
  check_status "docs" "${base_url}/docs" "${expected_docs_status}"
}

main "$@"
