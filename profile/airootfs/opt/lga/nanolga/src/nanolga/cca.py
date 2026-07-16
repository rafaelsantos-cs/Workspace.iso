"""CCA: selective four-role deliberation for ambiguous or risky plans."""

from __future__ import annotations

from typing import Any, Mapping

from .contracts import (
    CCAResult,
    CCAVerdict,
    Plan,
    RiskLevel,
    TaskRequest,
    risk_at_least,
)
from .providers import ModelProvider


class CognitiveChoiceAgent:
    def __init__(self, provider: ModelProvider, model: str) -> None:
        self.provider = provider
        self.model = model

    @staticmethod
    def should_activate(task: TaskRequest, plan: Plan) -> bool:
        return (
            plan.ambiguous
            or plan.cca_recommended
            or risk_at_least(task.risk_level, RiskLevel.HIGH)
            or any(
                risk_at_least(action.risk_level, RiskLevel.HIGH)
                for action in plan.actions
            )
        )

    async def deliberate(self, task: TaskRequest, plan: Plan) -> CCAResult:
        schema: Mapping[str, Any] = {
            "type": "object",
            "required": [
                "neutral_summary",
                "supporting_case",
                "opposing_case",
                "verdict",
                "confidence",
                "reasoning_summary",
                "required_human_approval",
            ],
            "properties": {
                "neutral_summary": {"type": "string"},
                "supporting_case": {"type": "string"},
                "opposing_case": {"type": "string"},
                "verdict": {
                    "type": "string",
                    "enum": ["approve", "revise", "reject", "needs_human"],
                },
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "reasoning_summary": {"type": "string"},
                "required_human_approval": {"type": "boolean"},
            },
        }
        data = await self.provider.generate_json(
            purpose="cca.deliberate",
            system_prompt=(
                "You are NanoLGA's selective Cognitive Choice Agent. Deliberate "
                "through four explicit roles: Neutral separates evidence from "
                "hypothesis; Pro defends the plan; Contra attacks it; Concluder "
                "returns a bounded verdict. Provide only a short reasoning summary, "
                "not hidden chain-of-thought. Do not authorize missing permissions."
            ),
            input_payload={"task": task.to_dict(), "plan": plan.to_dict()},
            schema=schema,
            model=self.model,
            max_output_tokens=min(1_200, max(384, task.token_budget // 4)),
        )
        try:
            verdict = CCAVerdict(str(data.get("verdict", "needs_human")))
        except ValueError:
            verdict = CCAVerdict.NEEDS_HUMAN
        confidence = max(0.0, min(1.0, float(data.get("confidence", 0.0))))
        required_human = bool(data.get("required_human_approval", False))
        if verdict is CCAVerdict.NEEDS_HUMAN:
            required_human = True
        return CCAResult(
            invoked=True,
            verdict=verdict,
            confidence=confidence,
            neutral_summary=str(data.get("neutral_summary", "")),
            supporting_case=str(data.get("supporting_case", "")),
            opposing_case=str(data.get("opposing_case", "")),
            reasoning_summary=str(data.get("reasoning_summary", "")),
            required_human_approval=required_human,
        )
