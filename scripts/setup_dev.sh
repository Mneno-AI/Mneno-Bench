#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-python3}"

"${PYTHON_BIN}" -m pip install -r requirements.txt
npm install

if [[ -n "${MNENO_WHEEL_PATH:-}" ]]; then
  "${PYTHON_BIN}" -m pip install "${MNENO_WHEEL_PATH}"
fi

echo "Development dependencies installed."
