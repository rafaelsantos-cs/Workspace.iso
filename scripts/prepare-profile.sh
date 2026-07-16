#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly ROOT_DIR
readonly RELENG_DIR="${ARCHISO_RELENG_DIR:-/usr/share/archiso/configs/releng}"
BUILD_ROOT="$(realpath -m -- "${WORKSPACE_BUILD_DIR:-$ROOT_DIR/build}")"
readonly BUILD_ROOT
readonly GENERATED_PROFILE="$BUILD_ROOT/profile"

if [[ ! -d "$RELENG_DIR" ]]; then
    echo "error: ArchISO releng profile not found at $RELENG_DIR" >&2
    echo "Install archiso on Arch Linux or set ARCHISO_RELENG_DIR." >&2
    exit 2
fi

case "$BUILD_ROOT" in
    "$ROOT_DIR"/build|/tmp/workspace-*) ;;
    *)
        echo "error: WORKSPACE_BUILD_DIR must be a /tmp/workspace-* path" >&2
        exit 2
        ;;
esac

rm -rf -- "$GENERATED_PROFILE"
mkdir -p -- "$BUILD_ROOT"
cp -a -- "$RELENG_DIR" "$GENERATED_PROFILE"

cp -a -- "$ROOT_DIR/profile/airootfs/." "$GENERATED_PROFILE/airootfs/"
install -m 0644 -- "$ROOT_DIR/profile/profiledef.sh" "$GENERATED_PROFILE/profiledef.sh"

awk 'NF && $1 !~ /^#/ && !seen[$1]++ { print $1 }' \
    "$RELENG_DIR/packages.x86_64" \
    "$ROOT_DIR/packages.workspace" \
    > "$GENERATED_PROFILE/packages.x86_64"

printf 'Prepared profile: %s\n' "$GENERATED_PROFILE"
printf 'Packages: %s\n' "$(wc -l < "$GENERATED_PROFILE/packages.x86_64")"
