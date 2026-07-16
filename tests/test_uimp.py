from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from uimp import UimpError, pack, scan, unpack, validate
from workspace_policy import load_policy


ROOT = Path(__file__).resolve().parents[1]
POLICY = load_policy(ROOT / "profile/airootfs/etc/lga/policy.toml")


class UimpTests(unittest.TestCase):
    def test_round_trip_arbitrary_payload(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "image.png"
            source.write_bytes(b"not-a-real-png\x00\x01")
            envelope = root / "image.uimp"
            pack(
                [source],
                envelope,
                source="agp-vision",
                destination="lga-core",
                protocol="vsp",
                protocol_version="1",
                priority="normal",
                context="test",
            )
            result = validate(envelope, POLICY)
            self.assertTrue(result["valid"])
            self.assertEqual(result["payload_count"], 1)
            destination = root / "unpacked"
            unpack(envelope, destination, POLICY)
            extracted = next((destination / "payload").iterdir())
            self.assertEqual(extracted.read_bytes(), source.read_bytes())

    def test_pack_requires_uimp_extension(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "data.bin"
            source.write_bytes(b"data")
            with self.assertRaises(UimpError):
                pack(
                    [source], root / "data.zip", source="test", destination="core",
                    protocol="binary", protocol_version="1", priority="normal", context="",
                )

    def test_path_traversal_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "evil.uimp"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("manifest.json", "{}")
                archive.writestr("../escape", "bad")
            with self.assertRaises(UimpError):
                validate(path, POLICY)

    def test_manifest_hash_tampering_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "data.json"
            source.write_text('{"ok":true}', encoding="utf-8")
            good = root / "good.uimp"
            pack(
                [source], good, source="test", destination="core", protocol="json",
                protocol_version="1", priority="low", context="",
            )
            bad = root / "bad.uimp"
            with zipfile.ZipFile(good, "r") as original, zipfile.ZipFile(bad, "w") as changed:
                for info in original.infolist():
                    data = original.read(info)
                    if info.filename.startswith("payload/"):
                        data += b"tampered"
                    changed.writestr(info.filename, data)
            with self.assertRaises(UimpError):
                validate(bad, POLICY)

    def test_scan_flags_uncatalogued_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "raw.txt"
            path.write_text("raw", encoding="utf-8")
            result = scan(Path(directory), POLICY)
            self.assertFalse(result["ok"])
            self.assertEqual(result["uncatalogued"], [str(path)])


if __name__ == "__main__":
    unittest.main()
