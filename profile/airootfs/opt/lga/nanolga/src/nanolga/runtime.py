"""Deterministic NanoLGA control plane and operational state machine."""

from __future__ import annotations

import asyncio

from .agps import AGPRegistry
from .brain import LGABrain
from .cca import CognitiveChoiceAgent
from .contracts import (
    AGPReport,
    CCAResult,
    CCAVerdict,
    OperationalState,
    Plan,
    ReportStatus,
    SafetyDecision,
    TaskRequest,
    TaskResult,
    TaskStatus,
)
from .mma import MemoryManager
from .safety import SafetySupervisor


_TRANSITIONS = {
    OperationalState.DEEP_STANDBY: {OperationalState.PRE_AWAKE},
    OperationalState.PRE_AWAKE: {
        OperationalState.AWAKE,
        OperationalState.TASK_FINALIZATION,
    },
    OperationalState.AWAKE: {OperationalState.TASK_FINALIZATION},
    OperationalState.TASK_FINALIZATION: {OperationalState.IDLE_LEARNING},
    OperationalState.IDLE_LEARNING: {OperationalState.DEEP_STANDBY},
}


class NanoLGARuntime:
    """Sequential v0.1 runtime.

    Parallel execution is intentionally deferred until ownership, leases and
    idempotency contracts exist.  A lock prevents two tasks from sharing this
    single logical Core concurrently.
    """

    def __init__(
        self,
        *,
        brain: LGABrain,
        cca: CognitiveChoiceAgent,
        mma: MemoryManager,
        agps: AGPRegistry,
        safety: SafetySupervisor,
        agp_timeout_seconds: float = 45.0,
    ) -> None:
        self.brain = brain
        self.cca = cca
        self.mma = mma
        self.agps = agps
        self.safety = safety
        self.agp_timeout_seconds = agp_timeout_seconds
        self.state = OperationalState.DEEP_STANDBY
        self._state_history: list[OperationalState] = [self.state]
        self._run_lock = asyncio.Lock()

    async def run(self, task: TaskRequest) -> TaskResult:
        async with self._run_lock:
            return await self._run_exclusive(task)

    async def _run_exclusive(self, task: TaskRequest) -> TaskResult:
        if self.state is not OperationalState.DEEP_STANDBY:
            raise RuntimeError(f"runtime entered a task from invalid state: {self.state}")
        self._state_history = [self.state]
        plan: Plan | None = None
        cca_result = CCAResult.not_invoked()
        reports: list[AGPReport] = []
        safety_decisions: list[SafetyDecision] = []
        memory_ids: tuple[str, ...] = ()

        try:
            self._transition(OperationalState.PRE_AWAKE)
            self.mma.append_event(task.task_id, "task.received", task.to_dict())

            # v0.1 pre-awake validates the event only. Wake-word and sensor
            # classifiers belong to future deployment adapters.
            self._transition(OperationalState.AWAKE)
            memories = self.mma.retrieve(task.objective, domain=task.domain)
            self.mma.append_event(
                task.task_id,
                "memory.retrieved",
                {
                    "count": len(memories),
                    "memory_ids": [memory.memory_id for memory in memories],
                },
            )

            plan = await self.brain.plan(task, memories, self.agps.catalog())
            self.mma.append_event(task.task_id, "core.plan", plan.to_dict())

            if self.cca.should_activate(task, plan):
                cca_result = await self.cca.deliberate(task, plan)
                self.mma.append_event(task.task_id, "cca.result", cca_result.to_dict())
                if cca_result.verdict is CCAVerdict.REJECT:
                    return self._finish(
                        task=task,
                        status=TaskStatus.BLOCKED,
                        answer="CCA rejected the proposed plan.",
                        plan=plan,
                        cca=cca_result,
                        reports=reports,
                        safety_decisions=safety_decisions,
                        memory_ids=memory_ids,
                    )
                if cca_result.verdict is CCAVerdict.REVISE:
                    return self._finish(
                        task=task,
                        status=TaskStatus.BLOCKED,
                        answer="CCA requested plan revision; v0.1 stopped safely.",
                        plan=plan,
                        cca=cca_result,
                        reports=reports,
                        safety_decisions=safety_decisions,
                        memory_ids=memory_ids,
                    )
                if (
                    cca_result.required_human_approval
                    and "human.approved" not in task.permissions
                ):
                    return self._finish(
                        task=task,
                        status=TaskStatus.BLOCKED,
                        answer="CCA requires explicit human approval.",
                        plan=plan,
                        cca=cca_result,
                        reports=reports,
                        safety_decisions=safety_decisions,
                        memory_ids=memory_ids,
                    )

            execution_status = TaskStatus.COMPLETED
            for action in plan.actions:
                safety_decision = self.safety.evaluate(action, task)
                safety_decisions.append(safety_decision)
                self.mma.append_event(
                    task.task_id,
                    "safety.decision",
                    {"action_id": action.action_id, **safety_decision.to_dict()},
                )
                if not safety_decision.allowed:
                    reports.append(
                        AGPReport(
                            agp_name=action.agp_name,
                            action_id=action.action_id,
                            status=ReportStatus.BLOCKED,
                            risk_level=action.risk_level,
                            error=safety_decision.reason,
                        )
                    )
                    execution_status = TaskStatus.BLOCKED
                    break

                agp = self.agps.get(action.agp_name)
                if agp is None:
                    reports.append(
                        AGPReport(
                            agp_name=action.agp_name,
                            action_id=action.action_id,
                            status=ReportStatus.FAILED,
                            risk_level=action.risk_level,
                            error=f"Unknown AGP: {action.agp_name}",
                        )
                    )
                    execution_status = TaskStatus.FAILED
                    break

                try:
                    report = await asyncio.wait_for(
                        agp.execute(action, task), timeout=self.agp_timeout_seconds
                    )
                except TimeoutError:
                    report = AGPReport(
                        agp_name=action.agp_name,
                        action_id=action.action_id,
                        status=ReportStatus.FAILED,
                        risk_level=action.risk_level,
                        error="AGP execution timed out",
                    )
                reports.append(report)
                self.mma.append_event(task.task_id, "agp.report", report.to_dict())
                if report.status is not ReportStatus.SUCCESS:
                    execution_status = (
                        TaskStatus.BLOCKED
                        if report.status is ReportStatus.BLOCKED
                        else TaskStatus.FAILED
                    )
                    break

            synthesis = await self.brain.synthesize(task, plan, cca_result, reports)
            memory_ids = self.brain.commit_memories(
                self.mma, synthesis.memory_candidates
            )
            return self._finish(
                task=task,
                status=execution_status,
                answer=synthesis.answer,
                plan=plan,
                cca=cca_result,
                reports=reports,
                safety_decisions=safety_decisions,
                memory_ids=memory_ids,
            )
        except Exception as exc:
            # Unexpected module failures are finalized and fail closed too.
            # asyncio.CancelledError inherits BaseException and is not swallowed.
            self.mma.append_event(
                task.task_id,
                "task.error",
                {"error_type": type(exc).__name__, "message": str(exc)},
            )
            return self._finish(
                task=task,
                status=TaskStatus.FAILED,
                answer="NanoLGA could not complete the task.",
                plan=plan,
                cca=cca_result,
                reports=reports,
                safety_decisions=safety_decisions,
                memory_ids=memory_ids,
                error=str(exc),
            )

    def _finish(
        self,
        *,
        task: TaskRequest,
        status: TaskStatus,
        answer: str,
        plan: Plan | None,
        cca: CCAResult,
        reports: list[AGPReport],
        safety_decisions: list[SafetyDecision],
        memory_ids: tuple[str, ...],
        error: str | None = None,
    ) -> TaskResult:
        if self.state in {OperationalState.PRE_AWAKE, OperationalState.AWAKE}:
            self._transition(OperationalState.TASK_FINALIZATION)
        elif self.state is not OperationalState.TASK_FINALIZATION:
            # Emergency normalization: never leave the runtime awake after an error.
            self.state = OperationalState.TASK_FINALIZATION
            self._state_history.append(self.state)

        self.mma.append_event(
            task.task_id,
            "task.finalized",
            {
                "status": status.value,
                "report_count": len(reports),
                "semantic_memory_ids": list(memory_ids),
                "error": error,
            },
        )
        self._transition(OperationalState.IDLE_LEARNING)
        idle_stats = self.mma.idle_learning()
        self.mma.append_event(task.task_id, "idle_learning.delta", idle_stats)
        self._transition(OperationalState.DEEP_STANDBY)
        return TaskResult(
            task_id=task.task_id,
            status=status,
            answer=answer,
            plan=plan,
            cca=cca,
            reports=tuple(reports),
            safety_decisions=tuple(safety_decisions),
            state_history=tuple(self._state_history),
            semantic_memory_ids=memory_ids,
            error=error,
        )

    def _transition(self, target: OperationalState) -> None:
        allowed = _TRANSITIONS[self.state]
        if target not in allowed:
            raise RuntimeError(f"invalid state transition: {self.state} -> {target}")
        self.state = target
        self._state_history.append(target)
