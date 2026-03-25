from __future__ import annotations

import subprocess
import sys


def run_step(label: str, command: list[str]) -> int:
    print(f"[smoke] {label}: {' '.join(command)}")
    result = subprocess.run(command)
    if result.returncode != 0:
        print(f"[smoke] FAIL: {label}")
    return result.returncode


def main() -> int:
    steps = [
        ("repo_hygiene", [sys.executable, "scripts/check_repo_hygiene.py"]),
        ("scheduler_dry_run_test", [sys.executable, "-m", "unittest", "tests.test_scheduler_dry_run", "-v"]),
    ]
    for label, command in steps:
        rc = run_step(label, command)
        if rc != 0:
            return rc

    print("[smoke] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
