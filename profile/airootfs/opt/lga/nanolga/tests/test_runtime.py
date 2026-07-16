from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from nanolga.contracts import (
    OperationalState,
    ReportStatus,
    RiskLevel,
    TaskRequest,
    TaskStatus,
)
from nanolga.factory import build_runtime


class RuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.runtime = build_runtime(
            database_path=Path(self.tempdir.name) / "runtime.db",
            provider="deterministic",
        )

    async def asyncTearDown(self) -> None:
        self.runtime.mma.close()
        self.tempdir.cleanup()

    async def test_calculator_runs_end_to_end(self) -> None:
        result = await self.runtime.run(
            TaskRequest(objective="Calcule 12 * (8 + 2)", domain="tests")
        )

        self.assertEqual(result.status, TaskStatus.COMPLETED)
        self.assertIn("120", result.answer)
        self.assertFalse(result.cca.invoked)
        self.assertEqual(result.reports[0].agp_name, "calculator")
        self.assertEqual(result.reports[0].status, ReportStatus.SUCCESS)
        self.assertEqual(result.state_history[0], OperationalState.DEEP_STANDBY)
        self.assertEqual(result.state_history[-1], OperationalState.DEEP_STANDBY)
        self.assertEqual(self.runtime.state, OperationalState.DEEP_STANDBY)
        self.assertEqual(len(result.semantic_memory_ids), 1)

    async def test_ambiguous_task_activates_cca(self) -> None:
        result = await self.runtime.run(
            TaskRequest(objective="Escolha talvez a melhor opção para o relatório")
        )

        self.assertEqual(result.status, TaskStatus.COMPLETED)
        self.assertTrue(result.cca.invoked)
        self.assertEqual(result.reports[0].agp_name, "general")

    async def test_high_risk_action_stops_without_human_approval(self) -> None:
        result = await self.runtime.run(
            TaskRequest(
                objective="Produza uma análise de risco",
                risk_level=RiskLevel.HIGH,
            )
        )

        self.assertEqual(result.status, TaskStatus.BLOCKED)
        self.assertTrue(result.cca.invoked)
        self.assertEqual(result.reports[0].status, ReportStatus.BLOCKED)
        self.assertIn("human", result.safety_decisions[0].reason.lower())

    async def test_human_approval_allows_high_risk_scoped_action(self) -> None:
        result = await self.runtime.run(
            TaskRequest(
                objective="Produza uma análise de risco",
                risk_level=RiskLevel.HIGH,
                permissions=frozenset({"human.approved"}),
            )
        )

        self.assertEqual(result.status, TaskStatus.COMPLETED)
        self.assertTrue(result.safety_decisions[0].allowed)


if __name__ == "__main__":
    unittest.main()
