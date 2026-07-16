#!/usr/bin/env bash
set -euo pipefail

readonly ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
for target in "$ROOT_DIR/build" "$ROOT_DIR/out" "$ROOT_DIR/work"; do
    case "$target" in
        "$ROOT_DIR"/build|"$ROOT_DIR"/out|"$ROOT_DIR"/work) rm -rf -- "$target" ;;
        *) echo "error: refusing unsafe cleanup path: $target" >&2; exit 2 ;;
    esac
done
