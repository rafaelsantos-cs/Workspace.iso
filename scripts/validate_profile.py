#!/usr/bin/env python3
"""Static validation for the WorkSpace ArchISO overlay."""

from __future__ import annotations

import json
import os
import re
import stat
import sys
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
AIROOTFS = ROOT / "profile" / "airootfs"


class ValidationFailure(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationFailure(message)


def text(relative: str) -> str:
    path = ROOT / relative
    require(path.is_file(), f"missing file: {relative}")
    return path.read_text(encoding="utf-8")


def validate_packages() -> None:
    packages = [line.strip() for line in text("packages.workspace").splitlines() if line.strip()]
    require(packages == sorted(packages), "packages.workspace must be sorted")
    require(len(packages) == len(set(packages)), "packages.workspace contains duplicates")
    required = {
        "blender",
        "bubblewrap",
        "chromium",
        "code",
        "dotnet-sdk-8.0",
        "jupyterlab",
        "networkmanager",
        "nftables",
        "plasma-desktop",
        "python",
        "sddm",
    }
    require(required.issubset(packages), f"required packages missing: {sorted(required-set(packages))}")
    require(not any(pkg.endswith(("-git", "-bin")) for pkg in packages), "AUR-style package in official manifest")


def validate_policy() -> None:
    policy_path = AIROOTFS / "etc/lga/policy.toml"
    policy = tomllib.loads(policy_path.read_text(encoding="utf-8"))
    require(policy.get("policy_version") == 1, "invalid policy version")
    require(policy["learning"].get("network_default") == "deny", "learning network must default deny")
    require(policy["browser"].get("autonomous_use") is False, "browser must remain supervised")
    require(policy["browser"].get("downloads") == "blocked", "browser downloads must be blocked")
    allowed = policy["learning"].get("allowed_executables", [])
    require(all(str(item).startswith("/usr/bin/") for item in allowed), "allowed executable outside /usr/bin")
    hosts = policy["egress"].get("allowed_hosts", [])
    require(hosts == sorted(hosts), "egress allowlist must be sorted")
    require(len(hosts) == len(set(hosts)), "egress allowlist contains duplicates")


def validate_architecture() -> None:
    architecture = tomllib.loads(
        (AIROOTFS / "etc/lga/architecture.toml").read_text(encoding="utf-8")
    )
    require(
        architecture.get("name") == "Learning Generative Architecture",
        "canonical LGA expansion is invalid",
    )
    require(architecture.get("spec_version") == "0.3.0", "invalid LGA spec version")
    require(
        architecture["boundaries"].get("workspace") == "external-client",
        "WorkSpace must remain outside the LTCA",
    )
    require(
        architecture["boundaries"].get("lusc_access") == "mma-only",
        "MMA must be the only LUSC ingress/egress",
    )
    require(
        architecture["v1"].get("request_path")
        == ["workspace-cli", "ltca-ingress", "deepbrain-v1"],
        "invalid canonical v1 request path",
    )
    require(
        architecture["v1"].get("memory_path")
        == ["deepbrain-v1", "mma-minimal", "lusc"],
        "invalid canonical v1 memory path",
    )
    require(
        architecture["components"]["agp"].get("expansion")
        == "Assistant Generative Processor",
        "invalid AGP expansion",
    )
    require(
        architecture["components"]["cca"].get("expansion")
        == "Cognitive Choice Agent",
        "invalid CCA expansion",
    )
    require(
        architecture["components"]["lam"].get("expansion")
        == "LGA Asynchronous Messaging",
        "invalid LAM expansion",
    )
    require(
        architecture["components"]["lip"].get("authority") == "none",
        "a LIP must not receive cognitive authority",
    )
    require(
        architecture["personas"]["ezlia"].get("installed") is True
        and architecture["personas"]["ezlia"].get("default") is False,
        "Ezlia must be installed but optional",
    )

    client = tomllib.loads(
        (AIROOTFS / "etc/lga/client.toml").read_text(encoding="utf-8")
    )
    require(client.get("config_version") == 1, "invalid LGA client config version")
    require(client["ltca"].get("endpoint") == "", "release must not embed an LTCA endpoint")
    require(
        client["interaction"].get("persona") == "standard",
        "standard interaction must remain the default",
    )
    require(
        client["interaction"].get("available_personas") == ["standard", "ezlia"],
        "installed persona catalog is invalid",
    )
    for relative in (
        "README.md",
        "docs/ARCHITECTURE.md",
        "profile/airootfs/opt/lga/nanolga/README.md",
    ):
        require(
            "Learning Generative Agent" not in text(relative),
            f"obsolete LGA expansion in {relative}",
        )


def validate_browser_policy() -> None:
    data = json.loads(
        (AIROOTFS / "etc/chromium/policies/managed/workspace.json").read_text(encoding="utf-8")
    )
    require(data.get("URLBlocklist") == ["*"], "Chromium must block by default")
    require(data.get("DownloadRestrictions") == 3, "Chromium downloads must be blocked")
    require(data.get("ExtensionInstallBlocklist") == ["*"], "Chromium extensions must be blocked")
    require(data.get("BrowserSignin") == 0 and data.get("SyncDisabled") is True, "Chromium sign-in/sync policy missing")


def validate_units() -> None:
    learning = text("profile/airootfs/etc/systemd/system/lga-learning@.service")
    egress = text("profile/airootfs/etc/systemd/system/lga-egressd.service")
    operator = text(
        "profile/airootfs/etc/systemd/system/workspace-operator-setup.service"
    )
    operator_script = text(
        "profile/airootfs/usr/local/libexec/workspace-operator-setup"
    )
    for directive in (
        "NoNewPrivileges=yes",
        "CapabilityBoundingSet=",
        "PrivateNetwork=yes",
        "ProtectHome=yes",
        "ProtectSystem=strict",
        "RestrictAddressFamilies=AF_UNIX",
        "MemoryMax=",
        "TasksMax=",
        "TimeoutStartSec=",
    ):
        require(directive in learning, f"learning service missing hardening: {directive}")
    require("PrivateNetwork=yes" not in egress, "egress service cannot use PrivateNetwork")
    for directive in (
        "NoNewPrivileges=yes",
        "CapabilityBoundingSet=",
        "ProtectHome=yes",
        "ProtectSystem=strict",
        "RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6",
    ):
        require(directive in egress, f"egress service missing hardening: {directive}")
    for directive in (
        "After=systemd-sysusers.service",
        "NoNewPrivileges=yes",
        "CapabilityBoundingSet=",
        "ProtectHome=read-only",
        "ProtectSystem=strict",
        "MemoryDenyWriteExecute=yes",
    ):
        require(directive in operator, f"operator verifier missing hardening: {directive}")
    require("ReadWritePaths=/etc" not in operator, "operator verifier must not write /etc")
    require("chpasswd" not in operator_script, "operator verifier must not mutate passwords")
    require("openssl rand" not in operator_script, "operator verifier must remain read-only")


def validate_release() -> None:
    version = text("VERSION").strip()
    release: dict[str, str] = {}
    for line in text("profile/airootfs/etc/workspace-release").splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        release[key] = value.strip().strip('"')
    require(release.get("VERSION") == version, "VERSION and workspace-release disagree")
    require(
        release.get("LGA_NAME") == "Learning Generative Architecture",
        "workspace-release has an invalid LGA name",
    )
    require(release.get("LGA_SPEC_VERSION") == "0.3.0", "invalid release LGA spec")
    require(
        release.get("LGA_WORKSPACE_BOUNDARY") == "external",
        "release boundary must identify WorkSpace as external",
    )
    require(f"## {version} -" in text("CHANGELOG.md"), "release missing from changelog")


def validate_files() -> None:
    required = [
        "profile/profiledef.sh",
        "profile/airootfs/root/customize_airootfs.sh",
        "profile/airootfs/etc/lga/architecture.toml",
        "profile/airootfs/etc/lga/client.toml",
        "profile/airootfs/etc/sudoers.d/10-workspace-operator",
        "profile/airootfs/usr/local/libexec/workspace-operator-setup",
        "profile/airootfs/usr/local/bin/nanolga",
        "profile/airootfs/usr/local/bin/nanolga-desktop-bridge",
        "profile/airootfs/usr/local/bin/uimp",
        "profile/airootfs/usr/local/bin/workspace-browser",
        "profile/airootfs/usr/local/bin/workspace-fetch",
        "profile/airootfs/usr/local/bin/workspace-job",
        "profile/airootfs/usr/local/lib/workspace/egressd.py",
        "profile/airootfs/usr/local/lib/workspace/job_runner.py",
        "profile/airootfs/usr/local/lib/workspace/uimp.py",
        "profile/airootfs/opt/lga/nanolga/pyproject.toml",
    ]
    for relative in required:
        path = ROOT / relative
        require(path.is_file(), f"missing required file: {relative}")
    for relative in (
        "scripts/build-iso.sh",
        "scripts/prepare-profile.sh",
        "scripts/validate.sh",
        "profile/airootfs/root/customize_airootfs.sh",
    ):
        mode = (ROOT / relative).stat().st_mode
        require(mode & stat.S_IXUSR, f"script is not executable: {relative}")
    for path in AIROOTFS.rglob("*"):
        require(not path.is_symlink(), f"unexpected symlink in overlay: {path.relative_to(ROOT)}")


def validate_secrets() -> None:
    secret_patterns = [
        re.compile(r"(?i)(groq|openai|github)[_-]?(api[_-]?)?key\s*=\s*['\"][A-Za-z0-9_-]{16,}"),
        re.compile(r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----"),
        re.compile(r"gh[opusr]_[A-Za-z0-9]{30,}"),
    ]
    excluded_suffixes = {".png", ".jpg", ".jpeg", ".pyc", ".db"}
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix.lower() in excluded_suffixes or "__pycache__" in path.parts:
            continue
        if path.stat().st_size > 2 * 1024 * 1024:
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for pattern in secret_patterns:
            require(not pattern.search(content), f"possible secret in {path.relative_to(ROOT)}")


def main() -> int:
    checks = [
        validate_packages,
        validate_policy,
        validate_architecture,
        validate_browser_policy,
        validate_units,
        validate_release,
        validate_files,
        validate_secrets,
    ]
    try:
        for check in checks:
            check()
            print(f"ok: {check.__name__}")
        print(f"profile validation passed: {len(checks)} checks")
        return 0
    except (OSError, KeyError, ValueError, ValidationFailure) as exc:
        print(f"profile validation failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
