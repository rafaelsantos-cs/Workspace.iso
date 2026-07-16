from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from workspace_policy import PolicyError, load_policy, validate_job_id


ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "profile/airootfs/etc/lga/policy.toml"


class PolicyTests(unittest.TestCase):
    def test_repository_policy_loads(self) -> None:
        policy = load_policy(POLICY)
        self.assertEqual(policy["learning"]["network_default"], "deny")

    def test_job_id_is_bounded(self) -> None:
        self.assertEqual(validate_job_id("study-01.py"), "study-01.py")
        for value in ("", "../escape", "/absolute", "space here", "a" * 65):
            with self.subTest(value=value), self.assertRaises(PolicyError):
                validate_job_id(value)

    def test_world_writable_policy_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "policy.toml"
            path.write_bytes(POLICY.read_bytes())
            path.chmod(0o666)
            with self.assertRaises(PolicyError):
                load_policy(path)


if __name__ == "__main__":
    unittest.main()
