#!/usr/bin/env bash
set -euo pipefail

ruff format benchmarks tests
ruff check --fix benchmarks tests
