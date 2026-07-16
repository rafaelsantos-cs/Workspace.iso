from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PrepareProfileTests(unittest.TestCase):
    def test_releng_is_copied_and_packages_are_merged_once(self) -> None:
        with tempfile.TemporaryDirectory(prefix="workspace-profile-") as directory:
            temp = Path(directory)
            releng = temp / "releng"
            (releng / "airootfs/etc").mkdir(parents=True)
            (releng / "packages.x86_64").write_text("base\npython\n", encoding="utf-8")
            (releng / "pacman.conf").write_text("[options]\n", encoding="utf-8")
            (releng / "airootfs/etc/base-marker").write_text("releng\n", encoding="utf-8")
            build_root = temp / "generated"
            environment = {
                **os.environ,
                "ARCHISO_RELENG_DIR": str(releng),
                "WORKSPACE_BUILD_DIR": str(build_root),
            }
            completed = subprocess.run(
                [str(ROOT / "scripts/prepare-profile.sh")],
                cwd=ROOT,
                env=environment,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            profile = build_root / "profile"
            self.assertTrue((profile / "airootfs/etc/base-marker").is_file())
            self.assertTrue((profile / "airootfs/etc/lga/policy.toml").is_file())
            packages = (profile / "packages.x86_64").read_text(encoding="utf-8").splitlines()
            self.assertEqual(packages.count("python"), 1)
            self.assertIn("blender", packages)
            self.assertEqual((profile / "profiledef.sh").read_bytes(), (ROOT / "profile/profiledef.sh").read_bytes())

    def test_alternate_build_path_cannot_escape_tmp(self) -> None:
        with tempfile.TemporaryDirectory(prefix="workspace-profile-") as directory:
            temp = Path(directory)
            releng = temp / "releng"
            (releng / "airootfs").mkdir(parents=True)
            (releng / "packages.x86_64").write_text("base\n", encoding="utf-8")
            environment = {
                **os.environ,
                "ARCHISO_RELENG_DIR": str(releng),
                "WORKSPACE_BUILD_DIR": "/tmp/workspace-safe/../../workspace-escape",
            }
            completed = subprocess.run(
                [str(ROOT / "scripts/prepare-profile.sh")],
                cwd=ROOT,
                env=environment,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("WORKSPACE_BUILD_DIR", completed.stderr)


if __name__ == "__main__":
    unittest.main()
