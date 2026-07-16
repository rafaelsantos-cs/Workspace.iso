"""Model-provider boundary for NanoLGA.

The architecture never imports a vendor SDK.  Groq is accessed through its
OpenAI-compatible HTTP endpoint, while the deterministic provider keeps the
entire system testable without a network connection or API key.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from dataclasses import dataclass
from typing import Any, Mapping, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class ProviderError(RuntimeError):
    """A model provider failed without exposing credentials."""


class ProviderRateLimitError(ProviderError):
    def __init__(self, message: str, retry_after: float = 1.0) -> None:
        super().__init__(message)
        self.retry_after = max(0.1, retry_after)


@dataclass(frozen=True, slots=True)
class ModelPolicy:
    core_model: str = "openai/gpt-oss-20b"
    worker_model: str = "llama-3.1-8b-instant"
    cca_model: str = "openai/gpt-oss-20b"

    @classmethod
    def from_environment(cls) -> "ModelPolicy":
        defaults = cls()
        return cls(
            core_model=os.getenv("NANOLGA_CORE_MODEL", defaults.core_model),
            worker_model=os.getenv("NANOLGA_WORKER_MODEL", defaults.worker_model),
            cca_model=os.getenv("NANOLGA_CCA_MODEL", defaults.cca_model),
        )


class ModelProvider(Protocol):
    async def generate_json(
        self,
        *,
        purpose: str,
        system_prompt: str,
        input_payload: Mapping[str, Any],
        schema: Mapping[str, Any],
        model: str,
        max_output_tokens: int = 1_024,
    ) -> Mapping[str, Any]: ...


class GroqProvider:
    """Zero-dependency Groq chat-completions adapter with JSON mode."""

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str = "https://api.groq.com/openai/v1",
        timeout_seconds: float = 45.0,
        max_retries: int = 2,
    ) -> None:
        self._api_key = api_key or os.getenv("GROQ_API_KEY")
        if not self._api_key:
            raise ValueError("GROQ_API_KEY is required for the Groq provider")
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._max_retries = max(0, max_retries)

    async def generate_json(
        self,
        *,
        purpose: str,
        system_prompt: str,
        input_payload: Mapping[str, Any],
        schema: Mapping[str, Any],
        model: str,
        max_output_tokens: int = 1_024,
    ) -> Mapping[str, Any]:
        schema_text = json.dumps(schema, ensure_ascii=False, separators=(",", ":"))
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        f"{system_prompt}\n"
                        "Return only a valid JSON object. Do not use markdown. "
                        f"The object must follow this schema: {schema_text}"
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {"purpose": purpose, "input": input_payload},
                        ensure_ascii=False,
                    ),
                },
            ],
            "temperature": 0.1,
            "max_completion_tokens": max(64, max_output_tokens),
            "response_format": {"type": "json_object"},
        }

        for attempt in range(self._max_retries + 1):
            try:
                response = await asyncio.to_thread(self._request_once, payload)
                return self._parse_response(response)
            except ProviderRateLimitError as exc:
                if attempt >= self._max_retries:
                    raise
                await asyncio.sleep(min(exc.retry_after * (2**attempt), 10.0))

        raise ProviderError("Groq request exhausted retries")

    def _request_once(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        request = Request(
            f"{self._base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
                "User-Agent": "NanoLGA/0.1",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            try:
                retry_after = float(exc.headers.get("retry-after", "1") or 1)
            except (TypeError, ValueError):
                retry_after = 1.0
            try:
                body = json.loads(exc.read().decode("utf-8"))
                detail = body.get("error", {}).get("message", f"HTTP {exc.code}")
            except (json.JSONDecodeError, UnicodeDecodeError):
                detail = f"HTTP {exc.code}"
            if exc.code == 429:
                raise ProviderRateLimitError(
                    f"Groq rate limit reached: {detail}", retry_after
                ) from exc
            raise ProviderError(f"Groq request failed: {detail}") from exc
        except (URLError, TimeoutError) as exc:
            reason = getattr(exc, "reason", str(exc))
            raise ProviderError(f"Groq network request failed: {reason}") from exc

    @staticmethod
    def _parse_response(response: Mapping[str, Any]) -> Mapping[str, Any]:
        try:
            content = response["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError("Groq returned an unexpected response shape") from exc
        if isinstance(content, Mapping):
            return content
        if not isinstance(content, str):
            raise ProviderError("Groq returned non-text JSON content")
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            # Defensive fallback for a provider that wrapped valid JSON in prose.
            match = re.search(r"\{.*\}", content, flags=re.DOTALL)
            if not match:
                raise ProviderError("Groq returned malformed JSON") from exc
            try:
                parsed = json.loads(match.group(0))
            except json.JSONDecodeError as nested_exc:
                raise ProviderError("Groq returned malformed JSON") from nested_exc
        if not isinstance(parsed, Mapping):
            raise ProviderError("Groq JSON response must be an object")
        return parsed


class DeterministicProvider:
    """Offline reference behavior used by tests and the no-key demo.

    It is deliberately simple: it proves orchestration and contracts, not
    language intelligence.
    """

    async def generate_json(
        self,
        *,
        purpose: str,
        system_prompt: str,
        input_payload: Mapping[str, Any],
        schema: Mapping[str, Any],
        model: str,
        max_output_tokens: int = 1_024,
    ) -> Mapping[str, Any]:
        del system_prompt, schema, model, max_output_tokens
        if purpose == "brain.plan":
            return self._plan(input_payload)
        if purpose == "agp.general.execute":
            action = input_payload.get("action") or {}
            return {
                "output": {
                    "text": str(action.get("instruction", "Task processed offline."))
                },
                "evidence": ["deterministic offline processor"],
                "recommended_actions": [],
                "constraints": ["No external model was called."],
                "risk_level": str(action.get("risk_level", "low")),
            }
        if purpose == "cca.deliberate":
            task = input_payload.get("task") or {}
            risk = str(task.get("risk_level", "low"))
            needs_human = risk == "critical"
            return {
                "neutral_summary": "The plan was separated from its assumptions.",
                "supporting_case": "The scoped action can advance the objective.",
                "opposing_case": "Unexpected output remains possible.",
                "verdict": "needs_human" if needs_human else "approve",
                "confidence": 0.72,
                "reasoning_summary": "Offline CCA applied a conservative risk rule.",
                "required_human_approval": needs_human,
            }
        if purpose == "brain.synthesize":
            return self._synthesize(input_payload)
        raise ProviderError(f"Unsupported deterministic purpose: {purpose}")

    @staticmethod
    def _extract_expression(text: str) -> str | None:
        candidates = re.findall(r"[0-9][0-9\s+\-*/().%]*", text)
        if not candidates:
            return None
        expression = max(candidates, key=len).strip()
        if any(operator in expression for operator in "+-*/%"):
            return expression
        return None

    def _plan(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        task = payload.get("task") or {}
        objective = str(task.get("objective", ""))
        risk = str(task.get("risk_level", "low"))
        expression = self._extract_expression(objective)
        agp_name = "calculator" if expression else "general"
        parameters: dict[str, Any] = {}
        if expression:
            parameters["expression"] = expression
        ambiguous_markers = ("talvez", "maybe", "escolha", "decida", "ou ")
        ambiguous = any(marker in objective.lower() for marker in ambiguous_markers)
        return {
            "summary": f"Delegate a bounded task to AGP-{agp_name}.",
            "memory_query": objective,
            "ambiguous": ambiguous,
            "cca_recommended": ambiguous or risk in {"high", "critical"},
            "actions": [
                {
                    "agp_name": agp_name,
                    "instruction": objective,
                    "expected_output": "structured report",
                    "parameters": parameters,
                    "risk_level": risk,
                    "safety_class": "S3",
                    "required_permissions": [],
                    "cost_estimate_tokens": 128,
                    "rationale": "Smallest specialist capable of the task.",
                    "requires_human_approval": risk == "critical",
                }
            ],
        }

    @staticmethod
    def _synthesize(payload: Mapping[str, Any]) -> Mapping[str, Any]:
        task = payload.get("task") or {}
        reports = payload.get("reports") or []
        successful = [r for r in reports if r.get("status") == "success"]
        if not successful:
            return {
                "answer": "The task produced no successful AGP report.",
                "memory_candidates": [],
            }
        output = successful[-1].get("output") or {}
        if "result" in output:
            answer = f"Resultado: {output['result']}"
        else:
            answer = str(output.get("text") or json.dumps(output, ensure_ascii=False))
        return {
            "answer": answer,
            "memory_candidates": [
                {
                    "content": f"Task completed: {task.get('objective', '')}",
                    "kind": "decision",
                    "domain": str(task.get("domain", "general")),
                    "importance": 0.35,
                    "confidence": 0.75,
                    "relations": [],
                }
            ],
        }
