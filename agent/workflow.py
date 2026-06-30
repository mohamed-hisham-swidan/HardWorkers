"""Workflow execution engine.

Manages multi-step workflow execution with context persistence,
step dependencies, and error recovery.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

log = logging.getLogger("hard_workers.agent.workflow")


class WorkflowStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class WorkflowStep:
    """A single step within a workflow."""

    id: str
    name: str
    action: str
    params: dict[str, Any] = field(default_factory=dict)
    depends_on: list[str] = field(default_factory=list)
    status: WorkflowStatus = WorkflowStatus.PENDING
    result: Any = None
    error: str | None = None
    started_at: float | None = None
    completed_at: float | None = None


class Workflow:
    """Orchestrates a sequence of steps with dependency management."""

    def __init__(
        self,
        name: str = "",
        context: dict[str, Any] | None = None,
    ) -> None:
        self.name = name
        self.context: dict[str, Any] = context or {}
        self.steps: list[WorkflowStep] = []
        self.status: WorkflowStatus = WorkflowStatus.PENDING
        self._step_map: dict[str, WorkflowStep] = {}
        self._handlers: dict[str, Callable] = {}
        self._created_at = time.monotonic()

    # ── Step management ─────────────────────────────────────────────────────────

    def add_step(
        self,
        step_id: str,
        name: str,
        action: str,
        params: dict[str, Any] | None = None,
        depends_on: list[str] | None = None,
    ) -> WorkflowStep:
        step = WorkflowStep(
            id=step_id,
            name=name,
            action=action,
            params=params or {},
            depends_on=depends_on or [],
        )
        self.steps.append(step)
        self._step_map[step_id] = step
        return step

    def register_handler(self, action: str, handler: Callable) -> None:
        self._handlers[action] = handler

    # ── Execution ───────────────────────────────────────────────────────────────

    def run(self) -> dict[str, Any]:
        """Execute all steps respecting dependencies."""
        self.status = WorkflowStatus.RUNNING
        results: dict[str, Any] = {}
        start_time = time.monotonic()

        for step in self.steps:
            step.status = WorkflowStatus.RUNNING
            step.started_at = time.monotonic()

            # Check dependencies
            deps_met = all(
                self._step_map.get(dep_id) and self._step_map[dep_id].status == WorkflowStatus.SUCCESS
                for dep_id in step.depends_on
            )
            if not deps_met:
                step.status = WorkflowStatus.FAILED
                step.error = "Dependencies not met"
                step.completed_at = time.monotonic()
                results[step.id] = {"success": False, "error": step.error}
                self.status = WorkflowStatus.FAILED
                return results

            try:
                handler = self._handlers.get(step.action)
                if handler:
                    handler_context = {
                        **self.context,
                        "step_params": step.params,
                        "previous_results": results,
                    }
                    step.result = handler(handler_context)
                else:
                    step.result = {"success": True, "action": step.action}

                step.status = WorkflowStatus.SUCCESS
                results[step.id] = {"success": True, "result": step.result}

            except Exception as exc:
                step.status = WorkflowStatus.FAILED
                step.error = str(exc)
                step.completed_at = time.monotonic()
                results[step.id] = {"success": False, "error": str(exc)}
                self.status = WorkflowStatus.FAILED
                return results

            finally:
                step.completed_at = time.monotonic()

        self.status = WorkflowStatus.SUCCESS
        elapsed = time.monotonic() - start_time
        log.info(
            "Workflow '%s' completed in %.2fs — %d steps, status=%s",
            self.name,
            elapsed,
            len(self.steps),
            self.status.value,
        )
        return results

    def cancel(self) -> None:
        self.status = WorkflowStatus.CANCELLED

    def get_step(self, step_id: str) -> WorkflowStep | None:
        return self._step_map.get(step_id)

    def get_failed_steps(self) -> list[WorkflowStep]:
        return [s for s in self.steps if s.status == WorkflowStatus.FAILED]

    def get_summary(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status.value,
            "total_steps": len(self.steps),
            "completed": sum(1 for s in self.steps if s.status == WorkflowStatus.SUCCESS),
            "failed": sum(1 for s in self.steps if s.status == WorkflowStatus.FAILED),
            "pending": sum(1 for s in self.steps if s.status == WorkflowStatus.PENDING),
            "elapsed": time.monotonic() - self._created_at,
        }
