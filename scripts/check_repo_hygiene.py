from __future__ import annotations

import fnmatch
import subprocess
import sys

# Patterns that must never be tracked in git.
BLOCKED_PATTERNS = [
    "**/__pycache__/**",
    "**/*.pyc",
    "**/*.pyo",
    "**/*.pyd",
    "**/*.db",
    "logs/*.xlsx",
]


def list_tracked_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files"],
        check=True,
        capture_output=True,
        text=True,
    )
    files = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    return files


def find_violations(files: list[str]) -> list[str]:
    violations: list[str] = []
    for path in files:
        normalized = path.replace("\\", "/")
        for pattern in BLOCKED_PATTERNS:
            if fnmatch.fnmatch(normalized, pattern):
                violations.append(normalized)
                break
    return sorted(violations)


def main() -> int:
    try:
        files = list_tracked_files()
    except subprocess.CalledProcessError as exc:
        print(f"[hygiene] Failed to list tracked files: {exc}")
        return 2

    violations = find_violations(files)
    if not violations:
        print("[hygiene] OK: no blocked generated artifacts are tracked.")
        return 0

    print("[hygiene] FAIL: blocked generated artifacts are tracked in git:")
    for file_path in violations:
        print(f"  - {file_path}")
    print("[hygiene] Remove with 'git rm --cached <file>' and commit the cleanup.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
