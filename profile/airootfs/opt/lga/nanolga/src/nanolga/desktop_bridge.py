"""JSON Lines bridge used by the native LGA Workspace desktop client.

The protocol keeps the UI and the reference runtime loosely coupled. Every
line on stdin is one request object and every line on stdout is one event or
result object. Human-readable diagnostics are written to stderr only.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import threading
from pathlib import Path
from typing import Any, Mapping

from .contracts import MemoryStatus, RiskLevel, TaskRequest
from .factory import ProviderName, build_runtime


class JsonLineEmitter:
    def __init__(self) -> None:
        self._lock = threading.Lock()

    def send(self, payload: Mapping[str, Any]) -> None:
        with self._lock:
            sys.stdout.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
            sys.stdout.flush()


def _source_for(event: str, payload: Mapping[str, Any]) -> str:
    if event.startswith("memory.") or event.startswith("idle_learning"):
        return "mma"
    if event.startswith("cca."):
        return "cca"
    if event.startswith("safety."):
        return "safety"
    if event.startswith("agp."):
        return f"agp-{payload.get('agp_name', 'unknown')}"
    if event.startswith("core.") or event.startswith("task."):
        return "core"
    return "runtime"


class DesktopBridge:
    def __init__(self, *, database_path: Path, provider: ProviderName) -> None:
        self.emitter = JsonLineEmitter()
        self.runtime = build_runtime(database_path=database_path, provider=provider)
        self._original_append_event = self.runtime.mma.append_event

        def append_and_stream(task_id: str, event_type: str, payload: Mapping[str, Any]) -> None:
            self._original_append_event(task_id, event_type, payload)
            self.emitter.send(
                {
                    "type": "runtime.event",
                    "event": event_type,
                    "source": _source_for(event_type, payload),
                    "task_id": task_id,
                    "payload": dict(payload),
                }
            )

        # MemoryManager has a deliberately small public surface. Wrapping this
        # instance method preserves persistence while exposing the same events
        # to the desktop without changing AGP contracts.
        self.runtime.mma.append_event = append_and_stream  # type: ignore[method-assign]

    def serve(self) -> int:
        for raw_line in sys.stdin:
            line = raw_line.strip()
            if not line:
                continue
            try:
                request = json.loads(line)
                if not isinstance(request, Mapping):
                    raise ValueError("request must be a JSON object")
                if self.handle(request) is False:
                    return 0
            except Exception as exc:  # protocol boundary: fail one request, keep bridge alive
                request_id = ""
                try:
                    request_id = str(request.get("request_id", ""))  # type: ignore[possibly-undefined]
                except Exception:
                    pass
                self.emitter.send(
                    {
                        "type": "bridge.error",
                        "request_id": request_id,
                        "error_type": type(exc).__name__,
                        "message": str(exc),
                    }
                )
        return 0

    def handle(self, request: Mapping[str, Any]) -> bool:
        request_type = str(request.get("type", ""))
        if request_type == "hello":
            self.emitter.send(
                {
                    "type": "bridge.ready",
                    "event": "bridge.ready",
                    "source": "bridge",
                    "task_id": "",
                    "payload": {
                        "protocol": 1,
                        "runtime": "NanoLGA",
                        "runtime_version": "0.1.0",
                        "client": request.get("client", "unknown"),
                    },
                }
            )
            return True
        if request_type == "task.submit":
            self._run_task(request)
            return True
        if request_type == "memory.list":
            self._list_memories(request)
            return True
        if request_type == "memory.feedback":
            self._memory_feedback(request)
            return True
        if request_type == "status.snapshot":
            self._status_snapshot(request)
            return True
        if request_type == "shutdown":
            return False
        raise ValueError(f"unsupported request type: {request_type or '<empty>'}")

    def _run_task(self, request: Mapping[str, Any]) -> None:
        request_id = str(request.get("request_id") or "")
        if not request_id:
            raise ValueError("request_id is required")
        objective = str(request.get("objective") or "").strip()
        if not objective:
            raise ValueError("objective is required")
        permissions = frozenset(str(item) for item in request.get("permissions") or ())
        task = TaskRequest(
            objective=objective,
            domain=str(request.get("domain") or "general"),
            constraints=tuple(str(item) for item in request.get("constraints") or ()),
            permissions=permissions,
            max_steps=int(request.get("max_steps", 4)),
            token_budget=int(request.get("token_budget", 4_000)),
            risk_level=RiskLevel(str(request.get("risk_level", "low"))),
            metadata={"desktop_request_id": request_id},
        )
        result = asyncio.run(self.runtime.run(task))
        self.emitter.send(
            {
                "type": "task.result",
                "request_id": request_id,
                "result": result.to_dict(),
            }
        )
        self.emitter.send(
            {
                "type": "runtime.state",
                "event": "runtime.state",
                "source": "runtime",
                "task_id": task.task_id,
                "payload": {"state": self.runtime.state.value},
            }
        )

    def _list_memories(self, request: Mapping[str, Any]) -> None:
        raw_status = request.get("status")
        status = MemoryStatus(str(raw_status)) if raw_status else None
        records = self.runtime.mma.list_memories(status=status, limit=int(request.get("limit", 100)))
        self.emitter.send(
            {
                "type": "memory.list.result",
                "request_id": str(request.get("request_id") or ""),
                "records": [record.to_dict() for record in records],
            }
        )

    def _memory_feedback(self, request: Mapping[str, Any]) -> None:
        memory_id = str(request.get("memory_id") or "")
        if not memory_id:
            raise ValueError("memory_id is required")
        verdict = str(request.get("verdict") or "")
        if verdict not in {"confirm", "contradict"}:
            raise ValueError("verdict must be confirm or contradict")
        record = self.runtime.mma.record_feedback(memory_id, confirmed=verdict == "confirm")
        self.emitter.send(
            {
                "type": "memory.feedback.result",
                "request_id": str(request.get("request_id") or ""),
                "record": record.to_dict(),
            }
        )

    def _status_snapshot(self, request: Mapping[str, Any]) -> None:
        self.emitter.send(
            {
                "type": "status.snapshot.result",
                "request_id": str(request.get("request_id") or ""),
                "state": self.runtime.state.value,
                "agps": self.runtime.agps.catalog(),
                "safety": {"critical_heartbeat": self.runtime.safety.critical_heartbeat},
                "memory": dict(self.runtime.mma.idle_learning()),
            }
        )

    def close(self) -> None:
        self.runtime.mma.append_event = self._original_append_event  # type: ignore[method-assign]
        self.runtime.mma.close()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="nanolga-desktop-bridge")
    parser.add_argument("--db", type=Path, default=Path(".nanolga/nanolga.db"))
    parser.add_argument("--provider", choices=["auto", "groq", "deterministic"], default="auto")
    return parser


def main() -> None:
    args = _parser().parse_args()
    bridge = DesktopBridge(database_path=args.db, provider=args.provider)
    try:
        raise SystemExit(bridge.serve())
    finally:
        bridge.close()


if __name__ == "__main__":
    main()
