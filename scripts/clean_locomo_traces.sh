#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RESULTS_ROOT="${1:-${RESULTS_DIR:-results}}"

if [[ "${RESULTS_ROOT}" != /* ]]; then
  RESULTS_ROOT="${PROJECT_ROOT}/${RESULTS_ROOT}"
fi

TRACE_DIR="${RESULTS_ROOT%/}/locomo/traces"

if [[ ! -d "${TRACE_DIR}" ]]; then
  echo "No LOCOMO traces found at ${TRACE_DIR}"
  exit 0
fi

FILE_COUNT="$(find "${TRACE_DIR}" -type f ! -name '.gitkeep' | wc -l | tr -d ' ')"
SIZE_BEFORE="$(du -sh "${TRACE_DIR}" | awk '{print $1}')"

if [[ "${FILE_COUNT}" == "0" ]]; then
  echo "No LOCOMO traces to remove at ${TRACE_DIR}"
  exit 0
fi

find "${TRACE_DIR}" -mindepth 1 ! -name '.gitkeep' -delete

echo "Removed ${FILE_COUNT} LOCOMO trace files (${SIZE_BEFORE}) from ${TRACE_DIR}"
