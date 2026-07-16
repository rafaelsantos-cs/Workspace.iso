#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly ROOT_DIR

if command -v docker >/dev/null 2>&1; then
    runtime=docker
elif command -v podman >/dev/null 2>&1; then
    runtime=podman
else
    echo "error: Podman or Docker is required" >&2
    exit 2
fi

mkdir -p -- "$ROOT_DIR/out"

# The variables in the script argument are expanded by bash inside the container.
# shellcheck disable=SC2016
"$runtime" run --rm --privileged \
    -v "$ROOT_DIR:/source:ro" \
    -v "$ROOT_DIR/out:/output" \
    -w /workspace \
    archlinux:latest \
    bash -lc '
        host_owner="$(stat -c %u:%g /source)"
        cp -a --no-preserve=ownership /source/. /workspace/
        pacman -Syu --noconfirm --needed archiso git shellcheck python
        ./scripts/build-iso.sh
        cp -a --no-preserve=ownership /workspace/out/. /output/
        chown -R "$host_owner" /output
    '
