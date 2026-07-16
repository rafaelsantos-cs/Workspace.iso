"""Replaceable Assistant Generative Processors.

AGPs receive only a bounded action and task metadata.  By construction, their
interface has no MMA reference and therefore no direct semantic-memory access.
"""

from __future__ import annotations

import ast
import operator
from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from .contracts import (
    AGPReport,
    ActionProposal,
    ReportStatus,
    RiskLevel,
    TaskRequest,
    max_risk,
)
from .providers import ModelProvider


class AGP(Protocol):
    name: str
    description: str

    async def execute(
        self, action: ActionProposal, task: TaskRequest
    ) -> AGPReport: ...


class AGPRegistry:
    def __init__(self) -> None:
        self._agps: dict[str, AGP] = {}

    def register(self, agp: AGP) -> None:
        if not agp.name.strip():
            raise ValueError("AGP name cannot be empty")
        self._agps[agp.name] = agp

    def get(self, name: str) -> AGP | None:
        return self._agps.get(name)

    def catalog(self) -> list[dict[str, str]]:
        return [
            {"name": agp.name, "description": agp.description}
            for agp in self._agps.values()
        ]


@dataclass(slots=True)
class GeneralAGP:
    provider: ModelProvider
    model: str
    name: str = "general"
    description: str = "General scoped text analysis and structured reporting."

    async def execute(self, action: ActionProposal, task: TaskRequest) -> AGPReport:
        schema = {
            "type": "object",
            "required": [
                "output",
                "evidence",
                "recommended_actions",
                "constraints",
                "risk_level",
            ],
            "properties": {
                "output": {"type": "object"},
                "evidence": {"type": "array", "items": {"type": "string"}},
                "recommended_actions": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "constraints": {"type": "array", "items": {"type": "string"}},
                "risk_level": {
                    "type": "string",
                    "enum": ["low", "medium", "high", "critical"],
                },
            },
        }
        data = await self.provider.generate_json(
            purpose="agp.general.execute",
            system_prompt=(
                "You are a replaceable NanoLGA specialist. Execute only the scoped "
                "instruction. Distinguish evidence from assumptions and never claim "
                "access to tools or data that were not provided."
            ),
            input_payload={
                "action": action.to_dict(),
                "task_context": {
                    "task_id": task.task_id,
                    "domain": task.domain,
                    "constraints": list(task.constraints),
                },
            },
            schema=schema,
            model=self.model,
            max_output_tokens=min(1_024, max(256, action.cost_estimate_tokens)),
        )
        try:
            reported_risk = RiskLevel(str(data.get("risk_level", "low")))
        except ValueError:
            reported_risk = action.risk_level
        return AGPReport(
            agp_name=self.name,
            action_id=action.action_id,
            status=ReportStatus.SUCCESS,
            output=dict(data.get("output") or {}),
            evidence=tuple(str(x) for x in data.get("evidence") or ()),
            recommended_actions=tuple(
                str(x) for x in data.get("recommended_actions") or ()
            ),
            constraints=tuple(str(x) for x in data.get("constraints") or ()),
            risk_level=max_risk(action.risk_level, reported_risk),
            cost_tokens=action.cost_estimate_tokens,
        )


class CalculatorAGP:
    name = "calculator"
    description = "Deterministic arithmetic with no model or code execution."

    _binary_ops = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv,
        ast.Mod: operator.mod,
        ast.Pow: operator.pow,
    }
    _unary_ops = {ast.UAdd: operator.pos, ast.USub: operator.neg}

    async def execute(self, action: ActionProposal, task: TaskRequest) -> AGPReport:
        del task
        expression = str(action.parameters.get("expression", "")).strip()
        try:
            result = self._evaluate(expression)
            return AGPReport(
                agp_name=self.name,
                action_id=action.action_id,
                status=ReportStatus.SUCCESS,
                output={"expression": expression, "result": result},
                evidence=(f"Deterministically evaluated expression: {expression}",),
                risk_level=action.risk_level,
                cost_tokens=0,
            )
        except (ValueError, ZeroDivisionError, OverflowError) as exc:
            return AGPReport(
                agp_name=self.name,
                action_id=action.action_id,
                status=ReportStatus.FAILED,
                output={},
                constraints=("Only bounded arithmetic expressions are accepted.",),
                risk_level=action.risk_level,
                error=str(exc),
            )

    @classmethod
    def _evaluate(cls, expression: str) -> int | float:
        if not expression or len(expression) > 200:
            raise ValueError("invalid or oversized arithmetic expression")
        try:
            tree = ast.parse(expression, mode="eval")
        except SyntaxError as exc:
            raise ValueError("invalid arithmetic expression") from exc
        result = cls._eval_node(tree.body, depth=0)
        if isinstance(result, complex) or abs(float(result)) > 1e100:
            raise OverflowError("arithmetic result exceeded the safety bound")
        return result

    @classmethod
    def _eval_node(cls, node: ast.AST, *, depth: int) -> int | float:
        if depth > 32:
            raise ValueError("arithmetic expression is too deeply nested")
        if isinstance(node, ast.Constant):
            value = node.value
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                return value
        if isinstance(node, ast.UnaryOp) and type(node.op) in cls._unary_ops:
            return cls._unary_ops[type(node.op)](
                cls._eval_node(node.operand, depth=depth + 1)
            )
        if isinstance(node, ast.BinOp) and type(node.op) in cls._binary_ops:
            left = cls._eval_node(node.left, depth=depth + 1)
            right = cls._eval_node(node.right, depth=depth + 1)
            if isinstance(node.op, ast.Pow) and abs(float(right)) > 12:
                raise ValueError("exponent exceeds the safety bound")
            return cls._binary_ops[type(node.op)](left, right)
        raise ValueError("unsupported arithmetic operation")
