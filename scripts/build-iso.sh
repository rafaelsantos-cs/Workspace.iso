#!/usr/bin/env bash
set -euo pipefail

readonly ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly WORK_DIR="$ROOT_DIR/work"
readonly OUT_DIR="$ROOT_DIR/out"
readonly PROFILE_DIR="$ROOT_DIR/build/profile"

if [[ "$(id -u)" -ne 0 ]]; then
    echo "error: mkarchiso must run as root" >&2
    exit 2
fi
if ! command -v mkarchiso >/dev/null 2>&1; then
    echo "error: mkarchiso is not installed (pacman -S archiso)" >&2
    exit 2
fi

"$ROOT_DIR/scripts/validate.sh"
"$ROOT_DIR/scripts/prepare-profile.sh"
mkdir -p -- "$WORK_DIR" "$OUT_DIR"

mkarchiso -v -r -w "$WORK_DIR" -o "$OUT_DIR" "$PROFILE_DIR"

sha256sum "$OUT_DIR"/*.iso > "$OUT_DIR/SHA256SUMS"
printf 'ISO and checksum written to %s\n' "$OUT_DIR"
