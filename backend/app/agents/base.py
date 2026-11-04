"""Agent runtime: typed I/O, restricted tools/secrets, timeout, retries, cancellation, progress, logs.

Deliberately free of third-party imports so it is easy to test. Input/output models are any class
with `model_validate` (pydantic v2 models in practice).
"""
import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger("agents")


class PermissionDenied(Exception):
    pass


class NotImplementedYet(Exception):
    """Raised by agents whose stage has not been built. Surfaces honestly instead of faking output."""


class AgentCancelled(Exception):
    pass


@dataclass(frozen=True)
class AgentSpec:
    key: str
    name: str
    responsibilities: str
    stage: int
    input_model: Any
    output_model: Any
    allowed_tools: frozenset[str] = frozenset()
    allowed_secrets: frozenset[str] = frozenset()
    timeout_seconds: float = 300.0
    max_retries: int = 2
    retry_backoff_seconds: float = 1.0


class ToolBox:
    """Only hands out tools/secrets the agent's spec permits."""

    def __init__(self, spec: AgentSpec, tools: dict[str, Callable], secrets: dict[str, str]):
        self._spec, self._tools, self._secrets = spec, tools, secrets

    def tool(self, name: str) -> Callable:
        if name not in self._spec.allowed_tools:
            raise PermissionDenied(f"Agent '{self._spec.key}' may not use tool '{name}'")
        if name not in self._tools:
            raise PermissionDenied(f"Tool '{name}' is not available in this environment")
        return self._tools[name]

    def secret(self, name: str) -> str:
        if name not in self._spec.allowed_secrets:
            raise PermissionDenied(f"Agent '{self._spec.key}' may not read secret '{name}'")
        value = self._secrets.get(name, "")
        if not value:
            raise PermissionDenied(f"Secret '{name}' is not configured")
        return value


@dataclass
class RunContext:
    spec: AgentSpec
    toolbox: ToolBox
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)
    logs: list[dict] = field(default_factory=list)
    progress: float = 0.0
    on_progress: Callable[[float], Awaitable[None]] | None = None

    def log(self, level: str, message: str, **fields) -> None:
        entry = {"ts": time.time(), "level": level, "agent": self.spec.key, "msg": message, **fields}
        self.logs.append(entry)
        log.log(getattr(logging, level.upper(), logging.INFO), message, extra={"ctx": entry})

    def check_cancelled(self) -> None:
        if self.cancel_event.is_set():
            raise AgentCancelled()

    async def report(self, fraction: float) -> None:
        self.check_cancelled()
        self.progress = max(0.0, min(1.0, fraction))
        if self.on_progress:
            await self.on_progress(self.progress)


@dataclass
class RunResult:
    status: str  # succeeded|failed|cancelled|timed_out|not_implemented|permission_denied
    output: Any = None
    error: str | None = None
    attempts: int = 0
    logs: list[dict] = field(default_factory=list)


AgentFn = Callable[[Any, RunContext], Awaitable[Any]]


async def run_agent(
    spec: AgentSpec,
    fn: AgentFn,
    raw_input: dict,
    tools: dict[str, Callable] | None = None,
    secrets: dict[str, str] | None = None,
    cancel_event: asyncio.Event | None = None,
    on_progress: Callable[[float], Awaitable[None]] | None = None,
) -> RunResult:
    ctx = RunContext(spec, ToolBox(spec, tools or {}, secrets or {}), cancel_event or asyncio.Event(),
                     on_progress=on_progress)
    try:
        parsed = spec.input_model.model_validate(raw_input)
    except Exception as exc:
        ctx.log("error", "invalid input", error=str(exc))
        return RunResult("failed", error=f"Invalid input: {exc}", logs=ctx.logs)

    attempts = 0
    while True:
        attempts += 1
        ctx.log("info", "attempt started", attempt=attempts)
        try:
            ctx.check_cancelled()
            raw_out = await asyncio.wait_for(fn(parsed, ctx), timeout=spec.timeout_seconds)
            out = spec.output_model.model_validate(raw_out)
            ctx.log("info", "succeeded", attempt=attempts)
            return RunResult("succeeded", out, attempts=attempts, logs=ctx.logs)
        except AgentCancelled:
            ctx.log("warning", "cancelled")
            return RunResult("cancelled", attempts=attempts, logs=ctx.logs)
        except NotImplementedYet as exc:
            ctx.log("warning", "not implemented", detail=str(exc))
            return RunResult("not_implemented", error=str(exc), attempts=attempts, logs=ctx.logs)
        except PermissionDenied as exc:
            ctx.log("error", "permission denied", detail=str(exc))
            return RunResult("permission_denied", error=str(exc), attempts=attempts, logs=ctx.logs)
        except asyncio.TimeoutError:
            ctx.log("error", "timeout", attempt=attempts)
            err, status = f"Timed out after {spec.timeout_seconds}s", "timed_out"
        except Exception as exc:
            ctx.log("error", "attempt failed", attempt=attempts, error=str(exc))
            err, status = str(exc), "failed"
        if attempts > spec.max_retries:
            return RunResult(status, error=err, attempts=attempts, logs=ctx.logs)
        await asyncio.sleep(spec.retry_backoff_seconds * attempts)
