#!/usr/bin/env bash
set -euo pipefail

readonly ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"

if command -v podman >/dev/null 2>&1; then
    runtime=podman
elif command -v docker >/dev/null 2>&1; then
    runtime=docker
else
    echo "error: Podman or Docker is required" >&2
    exit 2
fi

"$runtime" run --rm --privileged \
    -v "$ROOT_DIR:/workspace" \
    -w /workspace \
    archlinux:latest \
    bash -lc 'pacman -Syu --noconfirm --needed archiso git shellcheck python && ./scripts/build-iso.sh && chown -R "$(stat -c %u:%g /workspace)" /workspace/out /workspace/build /workspace/work'
