"""Shared environment/config helpers for the reproducible entry points."""

from __future__ import annotations

import os
import shlex
from pathlib import Path
from typing import Iterable, Mapping


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _parse_env_line(line: str) -> tuple[str, str] | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None
    if stripped.startswith("export "):
        stripped = stripped[len("export ") :].strip()
    if "=" not in stripped:
        return None
    key, raw_value = stripped.split("=", 1)
    key = key.strip()
    if not key:
        return None

    raw_value = raw_value.strip()
    if raw_value and raw_value[0] in {"'", '"'}:
        try:
            parts = shlex.split(raw_value, comments=False, posix=True)
            value = parts[0] if parts else ""
        except ValueError:
            value = raw_value.strip("'\"")
    else:
        value = raw_value.split(" #", 1)[0].strip()
    return key, value


def load_env_file(
    path: str | Path | None,
    *,
    override: bool = False,
    missing_ok: bool = True,
) -> dict[str, str]:
    """Load simple KEY=VALUE env files without requiring python-dotenv."""

    if path is None:
        return {}
    env_path = Path(path).expanduser()
    if not env_path.is_absolute():
        env_path = repo_root() / env_path
    if not env_path.exists():
        if missing_ok:
            return {}
        raise FileNotFoundError(f"Env file does not exist: {env_path}")

    loaded: dict[str, str] = {}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        parsed = _parse_env_line(line)
        if parsed is None:
            continue
        key, value = parsed
        loaded[key] = value
        if override or key not in os.environ:
            os.environ[key] = value
    return loaded


def load_env_files(
    paths: Iterable[str | Path | None],
    *,
    override: bool = False,
    missing_ok: bool = True,
) -> dict[str, str]:
    loaded: dict[str, str] = {}
    for path in paths:
        loaded.update(load_env_file(path, override=override, missing_ok=missing_ok))
    return loaded


def apply_env(defaults: Mapping[str, str], *, override: bool = False) -> None:
    for key, value in defaults.items():
        if override or key not in os.environ:
            os.environ[key] = value

def require_env(keys: Iterable[str]) -> None:
    missing = [key for key in keys if not os.getenv(key)]
    if missing:
        rendered = ", ".join(missing)
        raise EnvironmentError(
            f"Missing required environment variable(s): {rendered}. "
            "Set them in eval_skill.env or pass --env-file."
        )
