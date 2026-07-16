"""Typed contracts exchanged by every NanoLGA module.

The module intentionally uses only the Python standard library. Contracts are
strict at module boundaries so that an AGP or model can be replaced without
giving it implicit access to the rest of the system.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Mapping, Sequence, TypeVar
from uuid import uuid4


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


class OperationalState(StrEnum):
    DEEP_STANDBY = "deep_standby"
    PRE_AWAKE = "pre_awake"
    AWAKE = "awake"
    TASK_FINALIZATION = "task_finalization"
    IDLE_LEARNING = "idle_learning"


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


_RISK_RANK = {
    RiskLevel.LOW: 0,
    RiskLevel.MEDIUM: 1,
    RiskLevel.HIGH: 2,
    RiskLevel.CRITICAL: 3,
}


def risk_at_least(value: RiskLevel, threshold: RiskLevel) -> bool:
    return _RISK_RANK[value] >= _RISK_RANK[threshold]


def max_risk(*values: RiskLevel) -> RiskLevel:
    return max(values, key=_RISK_RANK.__getitem__)


class SafetyClass(StrEnum):
    S0 = "S0"
    S1 = "S1"
    S2 = "S2"
    S3 = "S3"


class ReportStatus(StrEnum):
    SUCCESS = "success"
    FAILED = "failed"
    BLOCKED = "blocked"


class TaskStatus(StrEnum):
    COMPLETED = "completed"
    BLOCKED = "blocked"
    FAILED = "failed"


class CCAVerdict(StrEnum):
    APPROVE = "approve"
    REVISE = "revise"
    REJECT = "reject"
    NEEDS_HUMAN = "needs_human"


class SafetyOutcome(StrEnum):
    ALLOW = "allow"
    BLOCK = "block"
    REQUIRE_HUMAN = "require_human"


class MemoryKind(StrEnum):
    FACT = "fact"
    HYPOTHESIS = "hypothesis"
    DECISION = "decision"
    RULE = "rule"
    FAILURE = "failure"
    PROCEDURE = "procedure"


class MemoryStatus(StrEnum):
    CANDIDATE = "candidate"
    ACTIVE = "active"
    STALE = "stale"
    ARCHIVED = "archived"


EnumT = TypeVar("EnumT", bound=StrEnum)


def _enum_value(value: Any, enum_type: type[EnumT], default: EnumT) -> EnumT:
    try:
        return enum_type(value)
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True, slots=True)
class TaskRequest:
    objective: str
    domain: str = "general"
    constraints: tuple[str, ...] = ()
    permissions: frozenset[str] = frozenset()
    max_steps: int = 4
    token_budget: int = 4_000
    risk_level: RiskLevel = RiskLevel.LOW
    metadata: Mapping[str, Any] = field(default_factory=dict)
    task_id: str = field(default_factory=lambda: str(uuid4()))
    created_at: str = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        if not self.objective.strip():
            raise ValueError("objective cannot be empty")
        if not 1 <= self.max_steps <= 32:
            raise ValueError("max_steps must be between 1 and 32")
        if not 256 <= self.token_budget <= 1_000_000:
            raise ValueError("token_budget must be between 256 and 1,000,000")

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "objective": self.objective,
            "domain": self.domain,
            "constraints": list(self.constraints),
            "permissions": sorted(self.permissions),
            "max_steps": self.max_steps,
            "token_budget": self.token_budget,
            "risk_level": self.risk_level.value,
            "metadata": dict(self.metadata),
            "created_at": self.created_at,
        }


@dataclass(frozen=True, slots=True)
class ActionProposal:
    agp_name: str
    instruction: str
    expected_output: str = "structured report"
    parameters: Mapping[str, Any] = field(default_factory=dict)
    risk_level: RiskLevel = RiskLevel.LOW
    safety_class: SafetyClass = SafetyClass.S3
    required_permissions: tuple[str, ...] = ()
    cost_estimate_tokens: int = 256
    rationale: str = ""
    requires_human_approval: bool = False
    action_id: str = field(default_factory=lambda: str(uuid4()))

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ActionProposal":
        return cls(
            action_id=str(data.get("action_id") or uuid4()),
            agp_name=str(data.get("agp_name", "general")).strip() or "general",
            instruction=str(data.get("instruction", "")).strip(),
            expected_output=str(data.get("expected_output", "structured report")),
            parameters=dict(data.get("parameters") or {}),
            risk_level=_enum_value(
                data.get("risk_level"), RiskLevel, RiskLevel.LOW
            ),
            safety_class=_enum_value(
                data.get("safety_class"), SafetyClass, SafetyClass.S3
            ),
            required_permissions=tuple(data.get("required_permissions") or ()),
            cost_estimate_tokens=max(0, int(data.get("cost_estimate_tokens", 256))),
            rationale=str(data.get("rationale", "")),
            requires_human_approval=bool(
                data.get("requires_human_approval", False)
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["risk_level"] = self.risk_level.value
        payload["safety_class"] = self.safety_class.value
        payload["required_permissions"] = list(self.required_permissions)
        payload["parameters"] = dict(self.parameters)
        return payload


@dataclass(frozen=True, slots=True)
class Plan:
    summary: str
    actions: tuple[ActionProposal, ...]
    memory_query: str
    ambiguous: bool = False
    cca_recommended: bool = False

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Plan":
        raw_actions = data.get("actions") or []
        if not isinstance(raw_actions, Sequence) or isinstance(raw_actions, str):
            raise ValueError("plan.actions must be a list")
        actions = tuple(
            ActionProposal.from_dict(item)
            for item in raw_actions
            if isinstance(item, Mapping)
        )
        if not actions:
            raise ValueError("a plan must contain at least one action")
        return cls(
            summary=str(data.get("summary", "Execution plan")),
            actions=actions,
            memory_query=str(data.get("memory_query", "")),
            ambiguous=bool(data.get("ambiguous", False)),
            cca_recommended=bool(data.get("cca_recommended", False)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary,
            "actions": [action.to_dict() for action in self.actions],
            "memory_query": self.memory_query,
            "ambiguous": self.ambiguous,
            "cca_recommended": self.cca_recommended,
        }


@dataclass(frozen=True, slots=True)
class AGPReport:
    agp_name: str
    action_id: str
    status: ReportStatus
    output: Mapping[str, Any] = field(default_factory=dict)
    evidence: tuple[str, ...] = ()
    recommended_actions: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()
    risk_level: RiskLevel = RiskLevel.LOW
    cost_tokens: int = 0
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "agp_name": self.agp_name,
            "action_id": self.action_id,
            "status": self.status.value,
            "output": dict(self.output),
            "evidence": list(self.evidence),
            "recommended_actions": list(self.recommended_actions),
            "constraints": list(self.constraints),
            "risk_level": self.risk_level.value,
            "cost_tokens": self.cost_tokens,
            "error": self.error,
        }


@dataclass(frozen=True, slots=True)
class CCAResult:
    invoked: bool
    verdict: CCAVerdict
    confidence: float
    neutral_summary: str = ""
    supporting_case: str = ""
    opposing_case: str = ""
    reasoning_summary: str = ""
    required_human_approval: bool = False

    @classmethod
    def not_invoked(cls) -> "CCAResult":
        return cls(
            invoked=False,
            verdict=CCAVerdict.APPROVE,
            confidence=1.0,
            reasoning_summary="CCA not required for this task.",
        )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["verdict"] = self.verdict.value
        return payload


@dataclass(frozen=True, slots=True)
class SafetyDecision:
    outcome: SafetyOutcome
    reason: str
    safety_class: SafetyClass

    @property
    def allowed(self) -> bool:
        return self.outcome is SafetyOutcome.ALLOW

    def to_dict(self) -> dict[str, Any]:
        return {
            "outcome": self.outcome.value,
            "reason": self.reason,
            "safety_class": self.safety_class.value,
        }


@dataclass(frozen=True, slots=True)
class MemoryRecord:
    content: str
    kind: MemoryKind
    domain: str
    source_task_id: str
    importance: float = 0.5
    confidence: float = 0.5
    status: MemoryStatus = MemoryStatus.CANDIDATE
    origin: str = "lga_core"
    relations: tuple[str, ...] = ()
    confirmations: int = 0
    contradictions: int = 0
    memory_id: str = field(default_factory=lambda: str(uuid4()))
    created_at: str = field(default_factory=utc_now)
    last_confirmed_at: str | None = None

    def __post_init__(self) -> None:
        if not self.content.strip():
            raise ValueError("memory content cannot be empty")
        if not 0.0 <= self.importance <= 1.0:
            raise ValueError("importance must be between 0 and 1")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["kind"] = self.kind.value
        payload["status"] = self.status.value
        payload["relations"] = list(self.relations)
        return payload


@dataclass(frozen=True, slots=True)
class TaskResult:
    task_id: str
    status: TaskStatus
    answer: str
    plan: Plan | None
    cca: CCAResult
    reports: tuple[AGPReport, ...]
    safety_decisions: tuple[SafetyDecision, ...]
    state_history: tuple[OperationalState, ...]
    semantic_memory_ids: tuple[str, ...] = ()
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "status": self.status.value,
            "answer": self.answer,
            "plan": self.plan.to_dict() if self.plan else None,
            "cca": self.cca.to_dict(),
            "reports": [report.to_dict() for report in self.reports],
            "safety_decisions": [item.to_dict() for item in self.safety_decisions],
            "state_history": [state.value for state in self.state_history],
            "semantic_memory_ids": list(self.semantic_memory_ids),
            "error": self.error,
        }
