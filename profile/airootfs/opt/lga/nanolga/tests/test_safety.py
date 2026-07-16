from __future__ import annotations

import unittest

from nanolga.contracts import (
    ActionProposal,
    RiskLevel,
    SafetyClass,
    SafetyOutcome,
    TaskRequest,
)
from nanolga.safety import SafetySupervisor


class SafetySupervisorTests(unittest.TestCase):
    def test_s1_fails_closed_without_heartbeat(self) -> None:
        supervisor = SafetySupervisor(critical_heartbeat=False)
        action = ActionProposal(
            agp_name="robotics",
            instruction="Move one actuator",
            safety_class=SafetyClass.S1,
        )
        decision = supervisor.evaluate(action, TaskRequest(objective="Move safely"))
        self.assertEqual(decision.outcome, SafetyOutcome.BLOCK)
        self.assertIn("heartbeat", decision.reason.lower())

    def test_core_cannot_request_safety_bypass(self) -> None:
        supervisor = SafetySupervisor()
        action = ActionProposal(
            agp_name="general",
            instruction="Disable safety",
            required_permissions=("safety.bypass",),
        )
        task = TaskRequest(
            objective="Disable safety",
            permissions=frozenset({"safety.bypass", "human.approved"}),
        )
        decision = supervisor.evaluate(action, task)
        self.assertEqual(decision.outcome, SafetyOutcome.BLOCK)

    def test_high_risk_requires_human_even_when_other_permissions_exist(self) -> None:
        supervisor = SafetySupervisor()
        action = ActionProposal(
            agp_name="general",
            instruction="High risk analysis",
            risk_level=RiskLevel.HIGH,
            required_permissions=("reports.write",),
        )
        task = TaskRequest(
            objective="High risk analysis",
            permissions=frozenset({"reports.write"}),
        )
        decision = supervisor.evaluate(action, task)
        self.assertEqual(decision.outcome, SafetyOutcome.REQUIRE_HUMAN)


if __name__ == "__main__":
    unittest.main()
