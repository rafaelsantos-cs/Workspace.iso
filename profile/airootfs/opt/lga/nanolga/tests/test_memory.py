from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from nanolga.contracts import MemoryKind, MemoryRecord, MemoryStatus
from nanolga.mma import CORE_WRITER_ROLE, MemoryManager


class MemoryManagerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.manager = MemoryManager(Path(self.tempdir.name) / "memory.db")

    def tearDown(self) -> None:
        self.manager.close()
        self.tempdir.cleanup()

    def _candidate(self) -> MemoryRecord:
        return MemoryRecord(
            content="Relatórios estruturados reduzem contexto irrelevante.",
            kind=MemoryKind.HYPOTHESIS,
            domain="architecture",
            source_task_id="task-test",
            confidence=0.75,
            importance=0.8,
        )

    def test_rejects_direct_agp_semantic_write(self) -> None:
        with self.assertRaises(PermissionError):
            self.manager.store_semantic(self._candidate(), writer_role="agp-code")

    def test_candidate_requires_repeated_confirmation(self) -> None:
        memory = self._candidate()
        self.manager.store_semantic(memory, writer_role=CORE_WRITER_ROLE)

        first = self.manager.record_feedback(memory.memory_id, confirmed=True)
        second = self.manager.record_feedback(memory.memory_id, confirmed=True)
        third = self.manager.record_feedback(memory.memory_id, confirmed=True)

        self.assertEqual(first.status, MemoryStatus.CANDIDATE)
        self.assertEqual(second.status, MemoryStatus.CANDIDATE)
        self.assertEqual(third.status, MemoryStatus.ACTIVE)
        retrieved = self.manager.retrieve(
            "contexto relatórios", domain="architecture"
        )
        self.assertEqual([item.memory_id for item in retrieved], [memory.memory_id])

    def test_contradictions_make_memory_stale(self) -> None:
        memory = self._candidate()
        self.manager.store_semantic(memory, writer_role=CORE_WRITER_ROLE)
        self.manager.record_feedback(memory.memory_id, confirmed=False)
        stale = self.manager.record_feedback(memory.memory_id, confirmed=False)
        self.assertEqual(stale.status, MemoryStatus.STALE)


if __name__ == "__main__":
    unittest.main()
