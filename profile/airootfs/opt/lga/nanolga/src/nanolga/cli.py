"""Command-line interface for the NanoLGA reference prototype."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from .contracts import MemoryStatus, RiskLevel, TaskRequest, TaskResult
from .factory import build_runtime


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nanolga", description="Run the NanoLGA v0.1 reference prototype."
    )
    parser.add_argument(
        "--db", type=Path, default=None, help="SQLite state path (default: .nanolga/nanolga.db)"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    demo = subparsers.add_parser("demo", help="Run an offline deterministic demo")
    demo.add_argument("--json", action="store_true", help="Print the complete result JSON")

    run = subparsers.add_parser("run", help="Run one objective")
    run.add_argument("objective")
    run.add_argument("--domain", default="general")
    run.add_argument(
        "--provider", choices=["auto", "groq", "deterministic"], default="auto"
    )
    run.add_argument(
        "--risk", choices=[item.value for item in RiskLevel], default="low"
    )
    run.add_argument(
        "--permission", action="append", default=[], help="Grant a named permission"
    )
    run.add_argument("--max-steps", type=int, default=4)
    run.add_argument("--token-budget", type=int, default=4_000)
    run.add_argument("--json", action="store_true")

    memories = subparsers.add_parser("memories", help="List semantic memories")
    memories.add_argument(
        "--status", choices=[item.value for item in MemoryStatus], default=None
    )
    memories.add_argument("--limit", type=int, default=50)

    feedback = subparsers.add_parser(
        "feedback", help="Confirm or contradict one candidate memory"
    )
    feedback.add_argument("memory_id")
    feedback.add_argument("verdict", choices=["confirm", "contradict"])
    return parser


def _print_result(result: TaskResult, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return
    print(f"status: {result.status.value}")
    print(f"task_id: {result.task_id}")
    print(f"answer: {result.answer}")
    print(f"cca: {'invoked' if result.cca.invoked else 'not invoked'}")
    print(f"agps: {', '.join(report.agp_name for report in result.reports) or 'none'}")
    if result.semantic_memory_ids:
        print(f"memory candidates: {', '.join(result.semantic_memory_ids)}")
    if result.error:
        print(f"error: {result.error}", file=sys.stderr)


async def _run_command(args: argparse.Namespace) -> int:
    if args.command == "demo":
        runtime = build_runtime(database_path=args.db, provider="deterministic")
        task = TaskRequest(objective="Calcule 12 * (8 + 2)", domain="demo")
        result = await runtime.run(task)
        _print_result(result, as_json=args.json)
        runtime.mma.close()
        return 0 if result.status.value == "completed" else 1

    if args.command == "run":
        try:
            runtime = build_runtime(database_path=args.db, provider=args.provider)
            task = TaskRequest(
                objective=args.objective,
                domain=args.domain,
                permissions=frozenset(args.permission),
                max_steps=args.max_steps,
                token_budget=args.token_budget,
                risk_level=RiskLevel(args.risk),
            )
            result = await runtime.run(task)
            _print_result(result, as_json=args.json)
            runtime.mma.close()
            return 0 if result.status.value == "completed" else 1
        except (ValueError, OSError) as exc:
            print(f"configuration error: {exc}", file=sys.stderr)
            return 2

    runtime = build_runtime(database_path=args.db, provider="deterministic")
    try:
        if args.command == "memories":
            status = MemoryStatus(args.status) if args.status else None
            records = runtime.mma.list_memories(status=status, limit=args.limit)
            print(
                json.dumps(
                    [record.to_dict() for record in records],
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0
        if args.command == "feedback":
            record = runtime.mma.record_feedback(
                args.memory_id, confirmed=args.verdict == "confirm"
            )
            print(json.dumps(record.to_dict(), ensure_ascii=False, indent=2))
            return 0
    finally:
        runtime.mma.close()
    return 2


def main() -> None:
    args = _parser().parse_args()
    raise SystemExit(asyncio.run(_run_command(args)))


if __name__ == "__main__":
    main()
