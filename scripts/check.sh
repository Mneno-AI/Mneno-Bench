#!/usr/bin/env bash
set -euo pipefail

ruff check benchmarks tests
mypy benchmarks --ignore-missing-imports

if find tests -type f -name 'test_*.py' -print -quit | grep -q .; then
  PYTHONPATH=. pytest
fi

npm run build
npm run test:ui
