"""Deterministic safety authority outside the LGA model hierarchy."""

from __future__ import annotations

from dataclasses import dataclass, field

from .contracts import (
    ActionProposal,
    RiskLevel,
    SafetyClass,
    SafetyDecision,
    SafetyOutcome,
    TaskRequest,
    risk_at_least,
)


@dataclass(frozen=True, slots=True)
class SafetySupervisor:
    """Fail-closed policy gate.

    The Core can request an action but cannot modify these immutable blocks or
    turn a missing S0/S1 heartbeat into an authorization.
    """

    critical_heartbeat: bool = True
    immutable_blocked_permissions: frozenset[str] = field(
        default_factory=lambda: frozenset(
            {
                "safety.disable",
                "safety.bypass",
                "physical.override_e_stop",
            }
        )
    )

    def evaluate(self, action: ActionProposal, task: TaskRequest) -> SafetyDecision:
        requested = set(action.required_permissions)
        forbidden = requested.intersection(self.immutable_blocked_permissions)
        if forbidden:
            return SafetyDecision(
                outcome=SafetyOutcome.BLOCK,
                reason=f"Immutable safety capability denied: {sorted(forbidden)[0]}",
                safety_class=action.safety_class,
            )

        if action.safety_class in {SafetyClass.S0, SafetyClass.S1} and not self.critical_heartbeat:
            return SafetyDecision(
                outcome=SafetyOutcome.BLOCK,
                reason="Critical safety heartbeat missing; fail-safe block applied.",
                safety_class=action.safety_class,
            )

        missing = requested.difference(task.permissions)
        if missing:
            return SafetyDecision(
                outcome=SafetyOutcome.BLOCK,
                reason=f"Missing permission: {sorted(missing)[0]}",
                safety_class=action.safety_class,
            )

        requires_human = action.requires_human_approval or risk_at_least(
            action.risk_level, RiskLevel.HIGH
        )
        if requires_human and "human.approved" not in task.permissions:
            return SafetyDecision(
                outcome=SafetyOutcome.REQUIRE_HUMAN,
                reason="High-risk action requires explicit human approval.",
                safety_class=action.safety_class,
            )

        return SafetyDecision(
            outcome=SafetyOutcome.ALLOW,
            reason="Deterministic policy checks passed.",
            safety_class=action.safety_class,
        )
