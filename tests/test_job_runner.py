from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import job_runner
from job_runner import JobError, load_manifest, run
from workspace_policy import load_policy


ROOT = Path(__file__).resolve().parents[1]
POLICY = load_policy(ROOT / "profile/airootfs/etc/lga/policy.toml")


class JobRunnerTests(unittest.TestCase):
    def manifest(self, command: list[str]) -> dict[str, object]:
        return {
            "manifest_version": 1,
            "job_id": "unit-1",
            "command": command,
            "timeout_seconds": 10,
            "environment": {"PYTHONHASHSEED": "0"},
            "created_at": "2026-07-16T00:00:00+00:00",
        }

    def test_disallowed_executable_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            jobs = Path(directory) / "jobs"
            target = jobs / "unit-1"
            target.mkdir(parents=True)
            (target / "job.json").write_text(
                json.dumps(self.manifest(["/usr/bin/curl", "https://example.com"])),
                encoding="utf-8",
            )
            with patch.object(job_runner, "JOBS_ROOT", jobs), self.assertRaises(JobError):
                load_manifest("unit-1", POLICY)

    def test_python_job_runs_and_records_result(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            jobs = root / "jobs"
            workspaces = root / "workspaces"
            target = jobs / "unit-1"
            target.mkdir(parents=True)
            (target / "job.json").write_text(
                json.dumps(self.manifest(["/usr/bin/python3", "-c", "print('ok')"])),
                encoding="utf-8",
            )
            with patch.object(job_runner, "JOBS_ROOT", jobs), patch.object(
                job_runner, "WORKSPACES_ROOT", workspaces
            ):
                result = run("unit-1", POLICY)
            self.assertEqual(result["status"], "completed")
            self.assertEqual((target / "stdout.log").read_text(encoding="utf-8"), "ok\n")
            saved = json.loads((target / "result.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["return_code"], 0)


if __name__ == "__main__":
    unittest.main()
