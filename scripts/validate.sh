#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly ROOT_DIR
readonly OVERLAY_LIB="$ROOT_DIR/profile/airootfs/usr/local/lib/workspace"
readonly NANOLGA="$ROOT_DIR/profile/airootfs/opt/lga/nanolga"

printf 'Static profile validation\n'
python3 "$ROOT_DIR/scripts/validate_profile.py"

printf '\nShell syntax\n'
while IFS= read -r -d '' script; do
    bash -n "$script"
done < <(
    find "$ROOT_DIR/scripts" -type f -name '*.sh' -print0
    find "$ROOT_DIR/profile/airootfs/usr/local/bin" -type f -print0
    find "$ROOT_DIR/profile/airootfs/usr/local/libexec" -type f -print0
    find "$ROOT_DIR/profile/airootfs/root" -type f -name '*.sh' -print0
)

if command -v shellcheck >/dev/null 2>&1; then
    mapfile -d '' shell_files < <(
        find "$ROOT_DIR/scripts" -type f -name '*.sh' -print0
        find "$ROOT_DIR/profile/airootfs/usr/local/bin" -type f -print0
        find "$ROOT_DIR/profile/airootfs/usr/local/libexec" -type f -print0
        find "$ROOT_DIR/profile/airootfs/root" -type f -name '*.sh' -print0
    )
    shellcheck -x "${shell_files[@]}"
else
    printf 'skip: shellcheck is not installed\n'
fi

printf '\nPython compilation\n'
python3 -m compileall -q "$OVERLAY_LIB" "$NANOLGA/src" "$NANOLGA/tests" "$ROOT_DIR/tests"

printf '\nWorkSpace guard tests\n'
PYTHONPATH="$OVERLAY_LIB" python3 -m unittest discover -s "$ROOT_DIR/tests" -v

printf '\nNanoLGA tests\n'
PYTHONPATH="$NANOLGA/src" python3 -m unittest discover -s "$NANOLGA/tests" -v

printf '\nNanoLGA offline smoke test\n'
tmp_db="$(mktemp -p /tmp workspace-nanolga-XXXXXX.db)"
trap 'rm -f -- "$tmp_db" "$tmp_db-shm" "$tmp_db-wal"' EXIT
PYTHONPATH="$NANOLGA/src" NANOLGA_DB="$tmp_db" python3 -m nanolga demo --json >/dev/null

printf '\nAll locally available validations passed.\n'
