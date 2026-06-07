"""Container entrypoint that runs the demo and optionally stays available."""

from __future__ import annotations

import argparse
import signal
import subprocess
import sys
import time


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--keep-alive", action="store_true")
    args = parser.parse_args()

    completed = subprocess.run(
        [sys.executable, "-m", "benchmarks.mneno_suite.run"],
        check=False,
    )
    if completed.returncode != 0 or not args.keep_alive:
        return completed.returncode

    running = True

    def stop(_signum: int, _frame: object) -> None:
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    print("Bench container ready. Run: docker compose exec bench scripts/run_demo.sh")
    while running:
        time.sleep(1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
