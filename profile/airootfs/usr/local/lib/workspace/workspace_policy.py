"""Shared policy parsing and validation for WorkSpace services."""

from __future__ import annotations

import os
import re
import stat
import tomllib
from pathlib import Path
from typing import Any


JOB_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")


class PolicyError(ValueError):
    """The root-owned WorkSpace policy is invalid or unsafe."""


def validate_job_id(value: str) -> str:
    if not JOB_ID_PATTERN.fullmatch(value):
        raise PolicyError(
            "job id must be 1-64 ASCII letters, numbers, dot, underscore or dash"
        )
    if value in {".", ".."}:
        raise PolicyError("reserved job id")
    return value


def load_policy(path: str | Path, *, require_secure: bool = True) -> dict[str, Any]:
    policy_path = Path(path)
    try:
        info = policy_path.stat()
    except OSError as exc:
        raise PolicyError(f"cannot stat policy: {exc}") from exc
    if not stat.S_ISREG(info.st_mode):
        raise PolicyError("policy must be a regular file")
    if require_secure and info.st_mode & 0o022:
        raise PolicyError("policy must not be writable by group or others")
    if require_secure and os.geteuid() == 0 and info.st_uid != 0:
        raise PolicyError("policy must be owned by root")
    try:
        raw = policy_path.read_bytes()
        data = tomllib.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise PolicyError(f"cannot parse policy: {exc}") from exc
    if data.get("policy_version") != 1:
        raise PolicyError("unsupported policy_version")
    for section in ("learning", "egress", "uimp", "browser"):
        if not isinstance(data.get(section), dict):
            raise PolicyError(f"missing policy section: {section}")
    return data


def bounded_int(value: Any, *, name: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise PolicyError(f"{name} must be an integer")
    if not minimum <= value <= maximum:
        raise PolicyError(f"{name} must be between {minimum} and {maximum}")
    return value
