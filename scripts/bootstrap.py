from __future__ import annotations

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(__file__))


def run_step(label: str, command: list[str]) -> int:
    print(f"[bootstrap] {label}: {' '.join(command)}")
    completed = subprocess.run(command, cwd=ROOT)
    if completed.returncode != 0:
        print(f"[bootstrap] FAIL: {label}")
    return completed.returncode


def main() -> int:
    steps = [
        ("upgrade_pip", [sys.executable, "-m", "pip", "install", "--upgrade", "pip"]),
        ("install_requirements", [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"]),
        ("create_tables", [sys.executable, "criar_tabelas.py"]),
        ("hygiene_check", [sys.executable, "scripts/check_repo_hygiene.py"]),
        ("smoke_test", [sys.executable, "scripts/smoke_test.py"]),
    ]

    for label, command in steps:
        rc = run_step(label, command)
        if rc != 0:
            return rc

    print("[bootstrap] ambiente pronto")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
