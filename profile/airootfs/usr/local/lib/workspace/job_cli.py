#!/usr/bin/env python3
"""Operator-facing CLI for creating and controlling constrained jobs."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from workspace_policy import PolicyError, validate_job_id


JOBS_ROOT = Path("/var/lib/lga/jobs")
WORKSPACES_ROOT = Path("/var/lib/lga/workspaces")


def atomic_create(path: Path, payload: dict[str, object]) -> None:
    if path.exists():
        raise FileExistsError(f"manifest already exists: {path}")
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
        os.link(temporary, path)
        temporary.unlink()
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(prog="workspace-job")
    sub = parser.add_subparsers(dest="action", required=True)
    create = sub.add_parser("create")
    create.add_argument("job_id")
    create.add_argument("--timeout", type=int, default=900)
    create.add_argument("command", nargs=argparse.REMAINDER)
    for name in ("start", "stop", "show", "logs"):
        command = sub.add_parser(name)
        command.add_argument("job_id")
    args = parser.parse_args()
    try:
        job_id = validate_job_id(args.job_id)
        job_dir = JOBS_ROOT / job_id
        if args.action == "create":
            command = list(args.command)
            if command and command[0] == "--":
                command.pop(0)
            if not command:
                raise ValueError("command is required after --")
            job_dir.mkdir(parents=True, mode=0o2770, exist_ok=True)
            WORKSPACES_ROOT.joinpath(job_id).mkdir(parents=True, mode=0o2770, exist_ok=True)
            os.chmod(job_dir, 0o2770)
            os.chmod(WORKSPACES_ROOT / job_id, 0o2770)
            manifest = {
                "manifest_version": 1,
                "job_id": job_id,
                "command": command,
                "timeout_seconds": args.timeout,
                "environment": {},
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            atomic_create(job_dir / "job.json", manifest)
            print(json.dumps(manifest, ensure_ascii=False, indent=2))
            return 0
        if args.action in {"start", "stop"}:
            verb = "start" if args.action == "start" else "stop"
            return subprocess.run(
                ["systemctl", verb, f"lga-learning@{job_id}.service"], check=False
            ).returncode
        if args.action == "logs":
            return subprocess.run(
                ["journalctl", "--no-pager", "-u", f"lga-learning@{job_id}.service"],
                check=False,
            ).returncode
        for name in ("job.json", "result.json"):
            path = job_dir / name
            if path.is_file():
                print(path.read_text(encoding="utf-8"), end="")
        return 0
    except (OSError, ValueError, PolicyError) as exc:
        print(f"workspace-job: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
