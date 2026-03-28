#!/usr/bin/env python3
from __future__ import annotations

import fnmatch
import os
import pathlib
import re
import subprocess
import sys


REPO_ROOT = pathlib.Path(__file__).resolve().parent
SENSITIVE_ENV_NAMES = ("POCHI_PORTAL_API_KEY", "SECRET_KEY")
PLACEHOLDER_TOKENS = (
    "replace",
    "example",
    "issued-api-key",
    "your-",
    "dummy",
    "change-me",
    "changeme",
    "sample",
    "secret-here",
    "<",
    ">",
    "xxxxx",
    "todo",
    "秘密",
)
DIRECT_BLOCKED_PATHS = {
    "game.db",
    "data.db",
    "master_export.json",
}
PREFIX_BLOCKED_PATHS = (
    "venv/",
    ".venv/",
)
GLOB_BLOCKED_PATHS = (
    "game.db.bak.*",
)
ASSIGNMENT_PATTERNS = (
    re.compile(r"""(?:^|\b)POCHI_PORTAL_API_KEY\s*=\s*("?)([^"\s#]+)\1"""),
    re.compile(r"""["']?api_key["']?\s*[:=]\s*["']([A-Za-z0-9_-]{16,})["']"""),
    re.compile(r"""[?&]api_key=([A-Za-z0-9_-]{16,})"""),
)


def _run_git(*args: str, text: bool = True) -> str | bytes:
    result = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=text,
    )
    return result.stdout


def _staged_paths() -> list[str]:
    raw = _run_git("diff", "--cached", "--name-only", "-z", "--diff-filter=ACMR", text=False)
    if not raw:
        return []
    return [path for path in raw.decode("utf-8", errors="ignore").split("\0") if path]


def _is_env_file(path: str) -> bool:
    base = pathlib.PurePosixPath(path).name
    return base.startswith(".env") and not base.endswith(".example")


def _is_blocked_path(path: str) -> bool:
    if _is_env_file(path):
        return True
    if path in DIRECT_BLOCKED_PATHS:
        return True
    if any(path.startswith(prefix) for prefix in PREFIX_BLOCKED_PATHS):
        return True
    if any(fnmatch.fnmatch(path, pattern) for pattern in GLOB_BLOCKED_PATHS):
        return True
    return False


def _normalize_value(value: str) -> str:
    return value.strip().strip('"').strip("'").strip().rstrip(",")


def _is_placeholder(value: str) -> bool:
    lowered = _normalize_value(value).lower()
    if not lowered:
        return True
    return any(token in lowered for token in PLACEHOLDER_TOKENS)


def _looks_secret(value: str) -> bool:
    normalized = _normalize_value(value)
    if _is_placeholder(normalized):
        return False
    if len(normalized) < 16:
        return False
    return bool(re.fullmatch(r"[A-Za-z0-9_-]{16,}", normalized))


def _load_local_secret_values() -> dict[str, str]:
    values: dict[str, str] = {}
    for candidate in (".env.production", ".env", ".env.local"):
        path = REPO_ROOT / candidate
        if not path.exists():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            name, value = stripped.split("=", 1)
            name = name.strip()
            if name.startswith("export "):
                name = name[len("export ") :].strip()
            if name not in SENSITIVE_ENV_NAMES:
                continue
            normalized = _normalize_value(value)
            if _looks_secret(normalized):
                values[name] = normalized
    return values


def _staged_text(path: str) -> str:
    raw = _run_git("show", f":{path}", text=False)
    return raw.decode("utf-8", errors="ignore")


def main() -> int:
    staged_paths = _staged_paths()
    if not staged_paths:
        return 0

    blocked_paths = sorted(path for path in staged_paths if _is_blocked_path(path))
    local_secret_values = _load_local_secret_values()
    exact_secret_hits: list[tuple[str, str]] = []
    suspicious_value_hits: list[tuple[str, int, str]] = []

    for path in staged_paths:
        text = _staged_text(path)

        for env_name, secret_value in local_secret_values.items():
            if secret_value and secret_value in text:
                exact_secret_hits.append((path, env_name))

        for lineno, line in enumerate(text.splitlines(), start=1):
            for pattern in ASSIGNMENT_PATTERNS:
                match = pattern.search(line)
                if not match:
                    continue
                candidate = match.group(match.lastindex or 1)
                if _looks_secret(candidate):
                    suspicious_value_hits.append((path, lineno, _normalize_value(candidate)))

    if not blocked_paths and not exact_secret_hits and not suspicious_value_hits:
        return 0

    print("Commit blocked: possible secret leak or local-only file detected.", file=sys.stderr)

    if blocked_paths:
        print("", file=sys.stderr)
        print("Do not stage these local-only files:", file=sys.stderr)
        for path in blocked_paths:
            print(f"  - {path}", file=sys.stderr)

    if exact_secret_hits:
        print("", file=sys.stderr)
        print("Your staged changes include an exact value from a local env file:", file=sys.stderr)
        seen_exact: set[tuple[str, str]] = set()
        for path, env_name in exact_secret_hits:
            key = (path, env_name)
            if key in seen_exact:
                continue
            seen_exact.add(key)
            print(f"  - {path} contains {env_name}", file=sys.stderr)

    if suspicious_value_hits:
        print("", file=sys.stderr)
        print("Suspicious API-key-like values found in staged text:", file=sys.stderr)
        seen_suspicious: set[tuple[str, int]] = set()
        for path, lineno, _value in suspicious_value_hits:
            key = (path, lineno)
            if key in seen_suspicious:
                continue
            seen_suspicious.add(key)
            print(f"  - {path}:{lineno}", file=sys.stderr)

    print("", file=sys.stderr)
    print("Fix:", file=sys.stderr)
    print("  - Keep real keys only in .env.production", file=sys.stderr)
    print("  - Use git restore --staged <path> to unstage", file=sys.stderr)
    print("  - Prefer git add <explicit-file> instead of git add .", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
