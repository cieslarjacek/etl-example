#!/usr/bin/env bash
# Demo: load waves 1-3 into a running container and print the results.
# The CSV-to-JSON conversion runs inside the container, so the host
# needs only Docker and curl (and optionally jq for pretty output).
# Usage: scripts/demo.sh BASE_URL CONTAINER
set -euo pipefail

readonly USAGE="usage: demo.sh BASE_URL CONTAINER"

pretty_print() {
  if command -v jq >/dev/null; then
    jq .
  else
    cat
    echo
  fi
}

upload_wave() {
  local base_url="$1" container="$2" wave="$3"
  echo "== POST /batches  <-  data/wave${wave}.csv"
  docker exec "${container}" etl-example to-json "data/wave${wave}.csv" |
    curl --silent --show-error --fail-with-body \
      --header "Content-Type: application/json" --data-binary @- \
      "${base_url}/batches" |
    pretty_print
}

show_summary() {
  local base_url="$1" wave="$2"
  echo "== GET /waves/${wave}/summary"
  curl --silent --show-error --fail-with-body \
    "${base_url}/waves/${wave}/summary" | pretty_print
}

main() {
  local base_url="${1:?${USAGE}}"
  local container="${2:?${USAGE}}"
  local wave
  for wave in 1 2; do
    upload_wave "${base_url}" "${container}" "${wave}"
  done
  show_summary "${base_url}" 2
  upload_wave "${base_url}" "${container}" 3
  for wave in 2 3; do
    show_summary "${base_url}" "${wave}"
  done
}

main "$@"
