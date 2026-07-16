"""Composition root for a runnable NanoLGA."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from .agps import AGPRegistry, CalculatorAGP, GeneralAGP
from .brain import LGABrain
from .cca import CognitiveChoiceAgent
from .mma import MemoryManager, MemoryPolicy
from .providers import (
    DeterministicProvider,
    GroqProvider,
    ModelPolicy,
    ModelProvider,
)
from .runtime import NanoLGARuntime
from .safety import SafetySupervisor


ProviderName = Literal["auto", "groq", "deterministic"]


def build_runtime(
    *,
    database_path: str | Path | None = None,
    provider: ProviderName | ModelProvider = "auto",
    api_key: str | None = None,
    model_policy: ModelPolicy | None = None,
    memory_policy: MemoryPolicy | None = None,
    critical_heartbeat: bool = True,
) -> NanoLGARuntime:
    models = model_policy or ModelPolicy.from_environment()
    resolved_provider: ModelProvider
    if isinstance(provider, str):
        if provider == "auto":
            provider = "groq" if (api_key or os.getenv("GROQ_API_KEY")) else "deterministic"
        if provider == "groq":
            resolved_provider = GroqProvider(api_key=api_key)
        elif provider == "deterministic":
            resolved_provider = DeterministicProvider()
        else:
            raise ValueError(f"unknown provider: {provider}")
    else:
        resolved_provider = provider

    db_path = Path(
        database_path or os.getenv("NANOLGA_DB", ".nanolga/nanolga.db")
    )
    mma = MemoryManager(db_path, policy=memory_policy)
    brain = LGABrain(resolved_provider, models.core_model)
    cca = CognitiveChoiceAgent(resolved_provider, models.cca_model)
    registry = AGPRegistry()
    registry.register(CalculatorAGP())
    registry.register(GeneralAGP(resolved_provider, models.worker_model))
    safety = SafetySupervisor(critical_heartbeat=critical_heartbeat)
    return NanoLGARuntime(
        brain=brain,
        cca=cca,
        mma=mma,
        agps=registry,
        safety=safety,
    )
