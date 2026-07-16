from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DesktopBridgeTests(unittest.TestCase):
    def test_jsonl_round_trip_streams_events_and_result(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            env = os.environ.copy()
            env["PYTHONPATH"] = str(ROOT / "src")
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-u",
                    "-m",
                    "nanolga.desktop_bridge",
                    "--provider",
                    "deterministic",
                    "--db",
                    str(Path(temp) / "bridge.db"),
                ],
                cwd=ROOT,
                env=env,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
            )
            assert process.stdin is not None
            assert process.stdout is not None
            try:
                process.stdin.write(json.dumps({"type": "hello", "client": "test"}) + "\n")
                process.stdin.flush()
                ready = json.loads(process.stdout.readline())
                self.assertEqual(ready["type"], "bridge.ready")

                process.stdin.write(
                    json.dumps(
                        {
                            "type": "task.submit",
                            "request_id": "req-1",
                            "objective": "Calcule 12 * (8 + 2)",
                            "domain": "test",
                            "risk_level": "low",
                        }
                    )
                    + "\n"
                )
                process.stdin.flush()

                messages = []
                while True:
                    message = json.loads(process.stdout.readline())
                    messages.append(message)
                    if message.get("type") == "task.result":
                        break

                event_names = {message.get("event") for message in messages}
                self.assertIn("task.received", event_names)
                self.assertIn("core.plan", event_names)
                self.assertIn("agp.report", event_names)
                result = messages[-1]
                self.assertEqual(result["request_id"], "req-1")
                self.assertEqual(result["result"]["status"], "completed")
                self.assertEqual(result["result"]["answer"], "Resultado: 120")
            finally:
                process.stdin.write(json.dumps({"type": "shutdown"}) + "\n")
                process.stdin.flush()
                process.wait(timeout=5)
                if process.poll() is None:
                    process.kill()
                process.stdin.close()
                process.stdout.close()
                if process.stderr is not None:
                    process.stderr.close()
