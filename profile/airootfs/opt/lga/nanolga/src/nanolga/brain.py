"""LGA Core: strategy, delegation, synthesis and memory curation."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Mapping, Sequence

from .contracts import (
    AGPReport,
    ActionProposal,
    CCAResult,
    MemoryKind,
    MemoryRecord,
    MemoryStatus,
    Plan,
    RiskLevel,
    TaskRequest,
    max_risk,
)
from .mma import CORE_WRITER_ROLE, MemoryManager
from .providers import ModelProvider


@dataclass(frozen=True, slots=True)
class CoreSynthesis:
    answer: str
    memory_candidates: tuple[MemoryRecord, ...]


class LGABrain:
    writer_role = CORE_WRITER_ROLE

    def __init__(self, provider: ModelProvider, model: str) -> None:
        self.provider = provider
        self.model = model

    async def plan(
        self,
        task: TaskRequest,
        memories: Sequence[MemoryRecord],
        agp_catalog: Sequence[Mapping[str, str]],
    ) -> Plan:
        schema: Mapping[str, Any] = {
            "type": "object",
            "required": [
                "summary",
                "memory_query",
                "ambiguous",
                "cca_recommended",
                "actions",
            ],
            "properties": {
                "summary": {"type": "string"},
                "memory_query": {"type": "string"},
                "ambiguous": {"type": "boolean"},
                "cca_recommended": {"type": "boolean"},
                "actions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": [
                            "agp_name",
                            "instruction",
                            "expected_output",
                            "parameters",
                            "risk_level",
                            "safety_class",
                            "required_permissions",
                            "cost_estimate_tokens",
                            "rationale",
                            "requires_human_approval",
                        ],
                    },
                },
            },
        }
        data = await self.provider.generate_json(
            purpose="brain.plan",
            system_prompt=(
                "You are the NanoLGA Core. Operate at objective, strategy, priority "
                "and coordination level. Never pretend to execute a task yourself. "
                "Choose the smallest suitable AGP, respect the total budget, expose "
                "risk, and recommend CCA only for ambiguity, risk, or priority conflict."
            ),
            input_payload={
                "task": task.to_dict(),
                "available_agps": list(agp_catalog),
                "filtered_memory": [memory.to_dict() for memory in memories],
            },
            schema=schema,
            model=self.model,
            max_output_tokens=min(1_500, max(384, task.token_budget // 3)),
        )
        plan = Plan.from_dict(data)
        return self._enforce_plan_boundaries(plan, task, agp_catalog)

    @staticmethod
    def _enforce_plan_boundaries(
        plan: Plan,
        task: TaskRequest,
        agp_catalog: Sequence[Mapping[str, str]],
    ) -> Plan:
        available = {str(item["name"]) for item in agp_catalog}
        if not available:
            raise ValueError("no AGPs are registered")
        fallback = "general" if "general" in available else sorted(available)[0]
        bounded: list[ActionProposal] = []
        spent = 0
        for action in plan.actions[: task.max_steps]:
            cost = min(action.cost_estimate_tokens, task.token_budget)
            if bounded and spent + cost > task.token_budget:
                break
            agp_name = action.agp_name if action.agp_name in available else fallback
            instruction = action.instruction or task.objective
            bounded.append(
                replace(
                    action,
                    agp_name=agp_name,
                    instruction=instruction,
                    risk_level=max_risk(task.risk_level, action.risk_level),
                    cost_estimate_tokens=cost,
                )
            )
            spent += cost
        if not bounded:
            raise ValueError("plan exceeded task budget before its first action")
        return replace(plan, actions=tuple(bounded))

    async def synthesize(
        self,
        task: TaskRequest,
        plan: Plan,
        cca: CCAResult,
        reports: Sequence[AGPReport],
    ) -> CoreSynthesis:
        schema: Mapping[str, Any] = {
            "type": "object",
            "required": ["answer", "memory_candidates"],
            "properties": {
                "answer": {"type": "string"},
                "memory_candidates": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": [
                            "content",
                            "kind",
                            "domain",
                            "importance",
                            "confidence",
                            "relations",
                        ],
                    },
                },
            },
        }
        data = await self.provider.generate_json(
            purpose="brain.synthesize",
            system_prompt=(
                "You are the NanoLGA Core. Synthesize only from AGP reports and "
                "their evidence. Do not invent results. Propose at most three semantic "
                "memories; every proposal remains a candidate until confirmed."
            ),
            input_payload={
                "task": task.to_dict(),
                "plan": plan.to_dict(),
                "cca": cca.to_dict(),
                "reports": [report.to_dict() for report in reports],
            },
            schema=schema,
            model=self.model,
            max_output_tokens=min(1_500, max(384, task.token_budget // 3)),
        )
        answer = str(data.get("answer", "")).strip()
        if not answer:
            answer = "Task finished without a Core synthesis."
        candidates = self._curate_candidates(
            data.get("memory_candidates") or [], task
        )
        return CoreSynthesis(answer=answer, memory_candidates=tuple(candidates))

    @staticmethod
    def _curate_candidates(
        raw_candidates: Any, task: TaskRequest
    ) -> list[MemoryRecord]:
        if not isinstance(raw_candidates, Sequence) or isinstance(raw_candidates, str):
            return []
        curated: list[MemoryRecord] = []
        for raw in raw_candidates[:3]:
            if not isinstance(raw, Mapping):
                continue
            content = str(raw.get("content", "")).strip()
            if not content:
                continue
            try:
                kind = MemoryKind(str(raw.get("kind", "hypothesis")))
            except ValueError:
                kind = MemoryKind.HYPOTHESIS
            try:
                importance = max(0.0, min(1.0, float(raw.get("importance", 0.5))))
                confidence = max(0.0, min(1.0, float(raw.get("confidence", 0.5))))
            except (TypeError, ValueError):
                importance, confidence = 0.5, 0.5
            curated.append(
                MemoryRecord(
                    content=content,
                    kind=kind,
                    domain=str(raw.get("domain") or task.domain),
                    source_task_id=task.task_id,
                    importance=importance,
                    confidence=confidence,
                    status=MemoryStatus.CANDIDATE,
                    origin=CORE_WRITER_ROLE,
                    relations=tuple(str(x) for x in raw.get("relations") or ()),
                )
            )
        return curated

    def commit_memories(
        self, manager: MemoryManager, memories: Sequence[MemoryRecord]
    ) -> tuple[str, ...]:
        return tuple(
            manager.store_semantic(memory, writer_role=self.writer_role)
            for memory in memories
        )
