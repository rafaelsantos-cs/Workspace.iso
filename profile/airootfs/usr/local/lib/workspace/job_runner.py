#!/usr/bin/env python3
"""Execute one predeclared LGA job inside the systemd service boundary."""

from __future__ import annotations

import argparse
import json
import os
import resource
import signal
import stat
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from workspace_policy import PolicyError, bounded_int, load_policy, validate_job_id


JOBS_ROOT = Path("/var/lib/lga/jobs")
WORKSPACES_ROOT = Path("/var/lib/lga/workspaces")


class JobError(ValueError):
    """A job manifest is invalid or violates policy."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_regular_file(path: Path, limit: int) -> bytes:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise JobError(f"cannot open manifest: {exc}") from exc
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            raise JobError("manifest must be a regular file")
        if info.st_size > limit:
            raise JobError("manifest exceeds configured size")
        chunks = bytearray()
        while chunk := os.read(descriptor, min(65536, limit + 1 - len(chunks))):
            chunks.extend(chunk)
            if len(chunks) > limit:
                raise JobError("manifest exceeds configured size")
        return bytes(chunks)
    finally:
        os.close(descriptor)


def load_manifest(job_id: str, policy: dict[str, Any]) -> dict[str, Any]:
    learning = policy["learning"]
    max_manifest = bounded_int(
        learning.get("max_manifest_bytes"),
        name="learning.max_manifest_bytes",
        minimum=128,
        maximum=16 * 1024 * 1024,
    )
    raw = _read_regular_file(JOBS_ROOT / job_id / "job.json", max_manifest)
    try:
        manifest = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise JobError(f"invalid manifest JSON: {exc}") from exc
    if not isinstance(manifest, dict):
        raise JobError("manifest root must be an object")
    unknown = set(manifest).difference(
        {"manifest_version", "job_id", "command", "timeout_seconds", "environment", "created_at"}
    )
    if unknown:
        raise JobError(f"unknown manifest fields: {', '.join(sorted(unknown))}")
    if manifest.get("manifest_version") != 1 or manifest.get("job_id") != job_id:
        raise JobError("manifest version or job_id mismatch")
    command = manifest.get("command")
    if not isinstance(command, list) or not 1 <= len(command) <= 128:
        raise JobError("command must contain 1-128 arguments")
    if not all(isinstance(arg, str) and 0 < len(arg) <= 8192 and "\x00" not in arg for arg in command):
        raise JobError("command arguments must be bounded non-empty strings")
    allowed = learning.get("allowed_executables")
    if not isinstance(allowed, list) or not all(isinstance(item, str) for item in allowed):
        raise PolicyError("learning.allowed_executables must be a string list")
    if command[0] not in set(allowed):
        raise JobError(f"executable is not allowed: {command[0]}")
    timeout = bounded_int(
        manifest.get("timeout_seconds", 900),
        name="timeout_seconds",
        minimum=1,
        maximum=bounded_int(
            learning.get("max_timeout_seconds"),
            name="learning.max_timeout_seconds",
            minimum=1,
            maximum=86400,
        ),
    )
    environment = manifest.get("environment", {})
    if not isinstance(environment, dict) or len(environment) > 32:
        raise JobError("environment must be an object with at most 32 entries")
    raw_allowed_environment = learning.get("allowed_environment")
    if not isinstance(raw_allowed_environment, list) or not all(
        isinstance(item, str) for item in raw_allowed_environment
    ):
        raise PolicyError("learning.allowed_environment must be a string list")
    allowed_environment = set(raw_allowed_environment)
    clean_environment: dict[str, str] = {}
    for key, value in environment.items():
        if key not in allowed_environment:
            raise JobError(f"environment key is not allowed: {key}")
        if not isinstance(value, str) or len(value) > 4096 or "\x00" in value:
            raise JobError(f"environment value is invalid: {key}")
        clean_environment[key] = value
    return {**manifest, "command": command, "timeout_seconds": timeout, "environment": clean_environment}


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=path.parent,
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o640)
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _open_log(path: Path) -> int:
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    return os.open(path, flags, 0o600)


def _child_limits(max_output: int) -> None:
    resource.setrlimit(resource.RLIMIT_FSIZE, (max_output, max_output))
    os.umask(0o077)


def run(job_id: str, policy: dict[str, Any]) -> dict[str, Any]:
    manifest = load_manifest(job_id, policy)
    learning = policy["learning"]
    max_output = bounded_int(
        learning.get("max_output_bytes"),
        name="learning.max_output_bytes",
        minimum=1024,
        maximum=2**32,
    )
    job_dir = JOBS_ROOT / job_id
    workspace = WORKSPACES_ROOT / job_id
    if job_dir.is_symlink() or not job_dir.is_dir():
        raise JobError("job directory must be a real directory")
    if workspace.is_symlink():
        raise JobError("workspace must not be a symlink")
    workspace.mkdir(parents=True, exist_ok=True)
    home = workspace / ".home"
    temp = workspace / ".tmp"
    home.mkdir(mode=0o700, exist_ok=True)
    temp.mkdir(mode=0o700, exist_ok=True)
    environment = {
        "HOME": str(home),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PATH": "/usr/local/bin:/usr/bin",
        "TMPDIR": str(temp),
        "WORKSPACE_JOB_ID": job_id,
        **manifest["environment"],
    }
    stdout_fd = _open_log(job_dir / "stdout.log")
    stderr_fd = _open_log(job_dir / "stderr.log")
    started_at = utc_now()
    monotonic_start = time.monotonic()
    timed_out = False
    return_code: int | None = None
    try:
        process = subprocess.Popen(
            manifest["command"],
            cwd=workspace,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=stdout_fd,
            stderr=stderr_fd,
            shell=False,
            start_new_session=True,
            preexec_fn=lambda: _child_limits(max_output),
        )
        try:
            return_code = process.wait(timeout=manifest["timeout_seconds"])
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(process.pid, signal.SIGTERM)
            try:
                return_code = process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                return_code = process.wait(timeout=5)
    finally:
        os.close(stdout_fd)
        os.close(stderr_fd)
    result = {
        "job_id": job_id,
        "status": "timed_out" if timed_out else ("completed" if return_code == 0 else "failed"),
        "return_code": return_code,
        "timed_out": timed_out,
        "started_at": started_at,
        "finished_at": utc_now(),
        "duration_seconds": round(time.monotonic() - monotonic_start, 3),
        "command": manifest["command"],
        "stdout": str(job_dir / "stdout.log"),
        "stderr": str(job_dir / "stderr.log"),
    }
    _atomic_json(job_dir / "result.json", result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(prog="lga-job-runner")
    parser.add_argument("--policy", type=Path, default=Path("/etc/lga/policy.toml"))
    parser.add_argument("--job-id", required=True)
    args = parser.parse_args()
    try:
        job_id = validate_job_id(args.job_id)
        result = run(job_id, load_policy(args.policy))
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0 if result["status"] == "completed" else 1
    except (JobError, PolicyError, OSError, subprocess.SubprocessError) as exc:
        print(f"lga-job-runner: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
