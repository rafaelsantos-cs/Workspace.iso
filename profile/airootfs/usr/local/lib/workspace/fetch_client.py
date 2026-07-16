#!/usr/bin/env python3
"""Small client for the WorkSpace Unix-socket egress broker."""

from __future__ import annotations

import argparse
import json
import socket
import sys
import uuid
from pathlib import Path


MAX_RESPONSE = 128 * 1024


def main() -> int:
    parser = argparse.ArgumentParser(prog="workspace-fetch")
    parser.add_argument("url")
    parser.add_argument("--sha256", default=None)
    parser.add_argument("--socket", type=Path, default=Path("/run/lga/egress.sock"))
    args = parser.parse_args()
    request = {
        "request_id": str(uuid.uuid4()),
        "url": args.url,
        "expected_sha256": args.sha256,
    }
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(45)
            client.connect(str(args.socket))
            client.sendall((json.dumps(request) + "\n").encode("utf-8"))
            chunks = bytearray()
            while not chunks.endswith(b"\n"):
                chunk = client.recv(4096)
                if not chunk:
                    break
                chunks.extend(chunk)
                if len(chunks) > MAX_RESPONSE:
                    raise RuntimeError("broker response exceeds limit")
        response = json.loads(chunks.decode("utf-8"))
        print(json.dumps(response, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if response.get("ok") else 1
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, RuntimeError) as exc:
        print(f"workspace-fetch: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
