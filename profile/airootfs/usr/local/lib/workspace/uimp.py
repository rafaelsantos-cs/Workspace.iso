#!/usr/bin/env python3
"""UIMP 0.1 envelope packer, validator and safe extractor."""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import shutil
import stat
import sys
import tempfile
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, IO, Iterable

from workspace_policy import PolicyError, bounded_int, load_policy


UIMP_VERSION = "0.1"
DEFAULT_POLICY = Path("/etc/lga/policy.toml")
CHUNK_SIZE = 1024 * 1024


class UimpError(ValueError):
    """An envelope is malformed, unsafe or exceeds configured limits."""


def _sha256_stream(handle: IO[bytes]) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    while chunk := handle.read(CHUNK_SIZE):
        digest.update(chunk)
        size += len(chunk)
    return digest.hexdigest(), size


def _sha256_file(path: Path) -> tuple[str, int]:
    with path.open("rb") as handle:
        return _sha256_stream(handle)


def _safe_archive_name(name: str) -> str:
    if not name or "\\" in name or "\x00" in name:
        raise UimpError("invalid archive member name")
    path = PurePosixPath(name)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise UimpError(f"unsafe archive member: {name!r}")
    return path.as_posix()


def _zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = (stat.S_IFREG | 0o644) << 16
    return info


def _manifest_bytes(manifest: dict[str, Any]) -> bytes:
    return (
        json.dumps(
            manifest,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def pack(
    inputs: Iterable[Path],
    output: Path,
    *,
    source: str,
    destination: str,
    protocol: str,
    protocol_version: str,
    priority: str,
    context: str,
    message_id: str | None = None,
    created_at: str | None = None,
    policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    files = list(inputs)
    if not files:
        raise UimpError("at least one payload is required")
    if output.suffix.lower() != ".uimp":
        raise UimpError("outer envelope must use the .uimp extension")
    if output.exists():
        raise UimpError(f"refusing to overwrite existing output: {output}")
    if policy is not None:
        config = policy["uimp"]
        max_entries = bounded_int(
            config.get("max_entries"), name="uimp.max_entries", minimum=1, maximum=4096
        )
        if len(files) + 1 > max_entries:
            raise UimpError("payload count exceeds configured entry limit")
        max_file = bounded_int(
            config.get("max_file_bytes"), name="uimp.max_file_bytes", minimum=1, maximum=2**40
        )
        max_total = bounded_int(
            config.get("max_total_bytes"), name="uimp.max_total_bytes", minimum=1, maximum=2**42
        )
    else:
        max_file = 2**40
        max_total = 2**42
    payloads: list[dict[str, Any]] = []
    total_size = 0
    for index, path in enumerate(files):
        if path.is_symlink() or not path.is_file():
            raise UimpError(f"payload must be a regular non-symlink file: {path}")
        digest, size = _sha256_file(path)
        if size > max_file:
            raise UimpError(f"payload exceeds configured file limit: {path}")
        total_size += size
        if total_size > max_total:
            raise UimpError("payloads exceed configured total size")
        clean_name = Path(path.name).name.replace("\\", "_")
        archive_path = f"payload/{index:04d}-{clean_name}"
        media_type = mimetypes.guess_type(clean_name)[0] or "application/octet-stream"
        payloads.append(
            {
                "path": archive_path,
                "original_name": clean_name,
                "media_type": media_type,
                "sha256": digest,
                "size": size,
            }
        )
    manifest: dict[str, Any] = {
        "uimp_version": UIMP_VERSION,
        "message_id": message_id or str(uuid.uuid4()),
        "created_at": created_at or datetime.now(timezone.utc).isoformat(),
        "source": {"component": source},
        "destination": {"component": destination},
        "priority": priority,
        "context": context,
        "protocol": {
            "name": protocol,
            "version": protocol_version,
        },
        "payloads": payloads,
        "trace": [],
        "metadata": {},
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix=f".{output.name}.", suffix=".tmp", dir=output.parent, delete=False
        ) as temporary:
            temp_path = Path(temporary.name)
        with zipfile.ZipFile(
            temp_path, mode="w", compression=zipfile.ZIP_DEFLATED, compresslevel=6
        ) as archive:
            archive.writestr(_zip_info("manifest.json"), _manifest_bytes(manifest))
            for path, payload in zip(files, payloads, strict=True):
                archive.write(path, arcname=payload["path"])
        os.chmod(temp_path, 0o640)
        os.replace(temp_path, output)
        temp_path = None
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
    return manifest


def _read_manifest(archive: zipfile.ZipFile, max_bytes: int) -> dict[str, Any]:
    try:
        info = archive.getinfo("manifest.json")
    except KeyError as exc:
        raise UimpError("manifest.json is missing") from exc
    if info.file_size > max_bytes:
        raise UimpError("manifest exceeds configured size")
    try:
        data = json.loads(archive.read(info).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise UimpError(f"invalid manifest JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise UimpError("manifest root must be an object")
    return data


def _validate_manifest_shape(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    required = {
        "uimp_version",
        "message_id",
        "created_at",
        "source",
        "destination",
        "priority",
        "context",
        "protocol",
        "payloads",
        "trace",
        "metadata",
    }
    missing = sorted(required.difference(manifest))
    if missing:
        raise UimpError(f"manifest fields missing: {', '.join(missing)}")
    if manifest["uimp_version"] != UIMP_VERSION:
        raise UimpError(f"unsupported uimp_version: {manifest['uimp_version']!r}")
    try:
        uuid.UUID(str(manifest["message_id"]))
        parsed_time = datetime.fromisoformat(str(manifest["created_at"]).replace("Z", "+00:00"))
        if parsed_time.tzinfo is None:
            raise ValueError("timezone is required")
    except (ValueError, TypeError) as exc:
        raise UimpError("message_id or created_at is invalid") from exc
    for endpoint in ("source", "destination"):
        value = manifest[endpoint]
        if not isinstance(value, dict) or not isinstance(value.get("component"), str):
            raise UimpError(f"{endpoint}.component must be a string")
    protocol = manifest["protocol"]
    if not isinstance(protocol, dict) or not all(
        isinstance(protocol.get(key), str) for key in ("name", "version")
    ):
        raise UimpError("protocol name and version must be strings")
    payloads = manifest["payloads"]
    if not isinstance(payloads, list) or not payloads:
        raise UimpError("payloads must be a non-empty list")
    normalized: list[dict[str, Any]] = []
    for item in payloads:
        if not isinstance(item, dict):
            raise UimpError("each payload entry must be an object")
        if not all(
            key in item for key in ("path", "original_name", "media_type", "sha256", "size")
        ):
            raise UimpError("payload entry is incomplete")
        path = _safe_archive_name(str(item["path"]))
        if not path.startswith("payload/"):
            raise UimpError("payload path must be inside payload/")
        digest = str(item["sha256"]).lower()
        if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            raise UimpError("payload sha256 is invalid")
        if isinstance(item["size"], bool) or not isinstance(item["size"], int) or item["size"] < 0:
            raise UimpError("payload size is invalid")
        normalized.append({**item, "path": path, "sha256": digest})
    if len({item["path"] for item in normalized}) != len(normalized):
        raise UimpError("manifest contains duplicate payload paths")
    return normalized


def validate(path: Path, policy: dict[str, Any]) -> dict[str, Any]:
    uimp_policy = policy["uimp"]
    max_entries = bounded_int(
        uimp_policy.get("max_entries"), name="uimp.max_entries", minimum=1, maximum=4096
    )
    max_file = bounded_int(
        uimp_policy.get("max_file_bytes"),
        name="uimp.max_file_bytes",
        minimum=1,
        maximum=2**40,
    )
    max_total = bounded_int(
        uimp_policy.get("max_total_bytes"),
        name="uimp.max_total_bytes",
        minimum=1,
        maximum=2**42,
    )
    max_manifest = bounded_int(
        uimp_policy.get("max_manifest_bytes"),
        name="uimp.max_manifest_bytes",
        minimum=128,
        maximum=64 * 1024 * 1024,
    )
    if path.is_symlink() or not path.is_file():
        raise UimpError("envelope must be a regular non-symlink file")
    try:
        with zipfile.ZipFile(path, mode="r") as archive:
            infos = archive.infolist()
            if len(infos) > max_entries:
                raise UimpError("envelope has too many entries")
            names = [_safe_archive_name(info.filename) for info in infos]
            if len(names) != len(set(names)):
                raise UimpError("envelope contains duplicate archive entries")
            total = 0
            for info in infos:
                mode = info.external_attr >> 16
                if stat.S_ISLNK(mode):
                    raise UimpError(f"symlink entry is forbidden: {info.filename}")
                if info.flag_bits & 0x1:
                    raise UimpError("encrypted ZIP entries are forbidden")
                if info.file_size > max_file:
                    raise UimpError(f"entry exceeds file limit: {info.filename}")
                total += info.file_size
                if total > max_total:
                    raise UimpError("envelope exceeds total uncompressed size")
                if info.compress_size and info.file_size / info.compress_size > 1000:
                    raise UimpError(f"suspicious compression ratio: {info.filename}")
            manifest = _read_manifest(archive, max_manifest)
            payloads = _validate_manifest_shape(manifest)
            expected_names = {"manifest.json", *(item["path"] for item in payloads)}
            if set(names) != expected_names:
                raise UimpError("archive entries do not exactly match manifest payloads")
            for item in payloads:
                info = archive.getinfo(item["path"])
                if info.file_size != item["size"]:
                    raise UimpError(f"size mismatch: {item['path']}")
                with archive.open(info, "r") as handle:
                    digest, actual_size = _sha256_stream(handle)
                if actual_size != item["size"] or digest != item["sha256"]:
                    raise UimpError(f"hash mismatch: {item['path']}")
            corrupt = archive.testzip()
            if corrupt:
                raise UimpError(f"CRC failure: {corrupt}")
    except zipfile.BadZipFile as exc:
        raise UimpError(f"invalid ZIP container: {exc}") from exc
    return {
        "valid": True,
        "path": str(path),
        "message_id": manifest["message_id"],
        "uimp_version": manifest["uimp_version"],
        "payload_count": len(payloads),
        "uncompressed_bytes": sum(item["size"] for item in payloads),
        "manifest": manifest,
    }


def unpack(path: Path, destination: Path, policy: dict[str, Any]) -> dict[str, Any]:
    result = validate(path, policy)
    if destination.exists():
        raise UimpError(f"destination must not already exist: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.", dir=destination.parent)
    )
    try:
        with zipfile.ZipFile(path, mode="r") as archive:
            for info in archive.infolist():
                target = temporary.joinpath(*PurePosixPath(info.filename).parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
                if hasattr(os, "O_NOFOLLOW"):
                    flags |= os.O_NOFOLLOW
                descriptor = os.open(target, flags, 0o640)
                with os.fdopen(descriptor, "wb") as output, archive.open(info, "r") as source:
                    shutil.copyfileobj(source, output, CHUNK_SIZE)
        os.replace(temporary, destination)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return {**result, "destination": str(destination)}


def scan(directory: Path, policy: dict[str, Any]) -> dict[str, Any]:
    if not directory.is_dir():
        raise UimpError(f"scan target is not a directory: {directory}")
    valid: list[str] = []
    invalid: list[dict[str, str]] = []
    uncatalogued: list[str] = []
    for path in sorted(directory.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() != ".uimp":
            uncatalogued.append(str(path))
            continue
        try:
            validate(path, policy)
            valid.append(str(path))
        except (UimpError, PolicyError, OSError) as exc:
            invalid.append({"path": str(path), "error": str(exc)})
    return {
        "valid": valid,
        "invalid": invalid,
        "uncatalogued": uncatalogued,
        "ok": not invalid and not uncatalogued,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="uimp")
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    sub = parser.add_subparsers(dest="command", required=True)

    pack_parser = sub.add_parser("pack", help="pack one or more files")
    pack_parser.add_argument("inputs", nargs="+", type=Path)
    pack_parser.add_argument("--output", required=True, type=Path)
    pack_parser.add_argument("--source", default="unknown")
    pack_parser.add_argument("--destination", default="lga-core")
    pack_parser.add_argument("--protocol", default="binary")
    pack_parser.add_argument("--protocol-version", default="1")
    pack_parser.add_argument(
        "--priority", choices=("low", "normal", "high", "critical"), default="normal"
    )
    pack_parser.add_argument("--context", default="")

    validate_parser = sub.add_parser("validate", help="validate an envelope")
    validate_parser.add_argument("path", type=Path)

    inspect_parser = sub.add_parser("inspect", help="print a validated manifest")
    inspect_parser.add_argument("path", type=Path)

    unpack_parser = sub.add_parser("unpack", help="extract after validation")
    unpack_parser.add_argument("path", type=Path)
    unpack_parser.add_argument("destination", type=Path)

    scan_parser = sub.add_parser("scan", help="validate a directory of artifacts")
    scan_parser.add_argument("directory", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        policy = load_policy(args.policy)
        if args.command == "pack":
            result = pack(
                args.inputs,
                args.output,
                source=args.source,
                destination=args.destination,
                protocol=args.protocol,
                protocol_version=args.protocol_version,
                priority=args.priority,
                context=args.context,
                policy=policy,
            )
        elif args.command in {"validate", "inspect"}:
            result = validate(args.path, policy)
            if args.command == "inspect":
                result = result["manifest"]
            else:
                result.pop("manifest", None)
        elif args.command == "unpack":
            result = unpack(args.path, args.destination, policy)
            result.pop("manifest", None)
        else:
            result = scan(args.directory, policy)
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        if args.command == "scan" and not result["ok"]:
            return 1
        return 0
    except (UimpError, PolicyError, OSError) as exc:
        print(f"uimp: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
