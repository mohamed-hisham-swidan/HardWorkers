"""Core agent framework.

The agent follows a strict workflow:
Observe → Analyze → Plan → Execute → Verify → Retry → Report

Every modification is verified before the task is considered complete.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from agent.tools.code_analyzer import CodeAnalyzerTool
from agent.tools.file_io import FileIOTool

log = logging.getLogger("hard_workers.agent")

# Re-export for convenience
StepResult = Any


class AgentPhase(Enum):
    OBSERVE = "observe"
    ANALYZE = "analyze"
    PLAN = "plan"
    EXECUTE = "execute"
    VERIFY = "verify"
    RETRY = "retry"
    REPORT = "report"


@dataclass
class AgentConfig:
    """Configuration for the agent system."""

    workspace_dir: str | Path = "."
    max_retries: int = 3
    max_steps: int = 20
    verbose: bool = False
    safe_mode: bool = True
    allowed_paths: list[str] = field(default_factory=lambda: ["."])
    blocked_patterns: list[str] = field(
        default_factory=lambda: [
            ".env",
            ".git/",
            "__pycache__",
            "node_modules",
            ".venv",
            "venv/",
            ".pytest_cache",
        ]
    )


@dataclass
class AgentResult:
    """Result of an agent task execution."""

    success: bool
    summary: str
    steps_taken: int = 0
    files_modified: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    phase_results: dict[str, Any] = field(default_factory=dict)
    elapsed_seconds: float = 0.0
    final_state: str = ""


class Agent:
    """Autonomous coding agent with a structured workflow."""

    def __init__(
        self,
        config: AgentConfig | None = None,
        llm_call: Callable[..., str] | None = None,
    ) -> None:
        self.config = config or AgentConfig()
        self._llm = llm_call
        self._file_tool = FileIOTool(Path(self.config.workspace_dir))
        self._code_analyzer = CodeAnalyzerTool()
        self._lock = threading.Lock()
        self._context: dict[str, Any] = {}

    # ── Main execution ──────────────────────────────────────────────────────────

    def execute(
        self,
        task: str,
        context: dict[str, Any] | None = None,
        on_step: Callable[[AgentPhase, str], None] | None = None,
    ) -> AgentResult:
        """Execute a task following the Observe→Analyze→Plan→Execute→Verify→Retry→Report workflow."""
        t0 = time.monotonic()
        if context:
            self._context.update(context)
        self._context["task"] = task

        errors: list[str] = []
        files_modified: list[str] = []
        phase_results: dict[str, Any] = {}
        current_step = 0

        # Phase 1: Observe
        observation = self._observe(task)
        phase_results["observation"] = observation
        if on_step:
            on_step(AgentPhase.OBSERVE, observation)

        # Phase 2: Analyze
        analysis = self._analyze(task, observation)
        phase_results["analysis"] = analysis
        if on_step:
            on_step(AgentPhase.ANALYZE, analysis)

        # Phase 3: Plan
        plan = self._plan(task, analysis)
        phase_results["plan"] = plan
        if on_step:
            on_step(AgentPhase.PLAN, plan)

        if not plan.get("steps"):
            return AgentResult(
                success=True,
                summary="No steps needed — task already satisfied.",
                steps_taken=0,
                elapsed_seconds=time.monotonic() - t0,
            )

        # Phase 4-6: Execute → Verify → Retry loop
        for attempt in range(self.config.max_retries):
            current_step += 1
            if current_step > self.config.max_steps:
                errors.append("Max steps exceeded")
                break

            # Execute
            execution_result = self._execute_plan(plan, files_modified)
            phase_results[f"execute_{attempt}"] = execution_result
            if on_step:
                on_step(AgentPhase.EXECUTE, execution_result)

            # Verify
            verification = self._verify(task, execution_result)
            phase_results[f"verify_{attempt}"] = verification
            if on_step:
                on_step(AgentPhase.VERIFY, verification)

            if verification.get("success", False):
                break

            # Retry
            error = verification.get("error", "Verification failed")
            errors.append(f"Attempt {attempt + 1}: {error}")
            if attempt < self.config.max_retries - 1:
                plan = self._retry(task, plan, verification)
                phase_results[f"retry_{attempt}"] = plan
                if on_step:
                    on_step(AgentPhase.RETRY, f"Retrying: {error}")
            else:
                errors.append("Max retries reached")

        # Phase 7: Report
        report = self._report(task, errors, files_modified, phase_results)
        phase_results["report"] = report
        if on_step:
            on_step(AgentPhase.REPORT, report)

        elapsed = time.monotonic() - t0
        success = len(errors) == 0 or (
            len(errors) < self.config.max_retries
            and phase_results.get(f"verify_{self.config.max_retries - 1}", {}).get("success", False)
        )

        return AgentResult(
            success=success,
            summary=report,
            steps_taken=current_step,
            files_modified=files_modified,
            errors=errors,
            phase_results=phase_results,
            elapsed_seconds=elapsed,
            final_state=json.dumps(phase_results.get(f"verify_{self.config.max_retries - 1}", {}), indent=2),
        )

    # ── Phase implementations ───────────────────────────────────────────────────

    def _observe(self, task: str) -> str:
        """Phase 1: Observe the current state of the workspace."""
        observations: list[str] = [f"Task: {task}"]

        workspace = Path(self.config.workspace_dir)
        observations.append(f"Workspace: {workspace.resolve()}")

        if self._llm:
            prompt = f"Observe the current state for the task: {task}"
            try:
                llm_obs = self._llm(prompt)
                observations.append(f"LLM Observation: {llm_obs}")
            except Exception as exc:
                observations.append(f"LLM observation error: {exc}")

        return "\n".join(observations)

    def _analyze(self, task: str, observation: str) -> dict[str, Any]:
        """Phase 2: Analyze the task and determine what needs to be done."""
        analysis: dict[str, Any] = {
            "task": task,
            "complexity": self._estimate_complexity(task),
            "required_tools": self._detect_required_tools(task),
            "risks": self._assess_risks(task),
        }

        if self._llm:
            prompt = (
                f"Analyze this task and describe what needs to be done:\n{task}\n\n"
                f"Observation:\n{observation}\n\n"
                "Provide a concise analysis."
            )
            try:
                analysis["llm_analysis"] = self._llm(prompt)
            except Exception as exc:
                analysis["llm_analysis"] = f"Analysis error: {exc}"

        return analysis

    def _plan(self, task: str, analysis: dict[str, Any]) -> dict[str, Any]:
        """Phase 3: Create a step-by-step plan."""
        plan: dict[str, Any] = {
            "task": task,
            "steps": [],
            "estimated_impact": [],
        }

        required_tools = analysis.get("required_tools", [])
        for tool_type in required_tools:
            if tool_type == "read" and self._llm:
                plan["steps"].append({
                    "tool": "read",
                    "description": "Read relevant files",
                    "params": self._suggest_read_targets(task),
                })
            elif tool_type == "edit":
                plan["steps"].append({
                    "tool": "edit",
                    "description": "Modify files to implement changes",
                    "params": {},
                })
            elif tool_type == "create":
                plan["steps"].append({
                    "tool": "create",
                    "description": "Create new files",
                    "params": {},
                })
            elif tool_type == "analyze":
                plan["steps"].append({
                    "tool": "analyze",
                    "description": "Analyze code structure",
                    "params": {},
                })

        if not plan["steps"]:
            plan["steps"].append({
                "tool": "analyze",
                "description": "Examine task requirements",
                "params": {"task": task},
            })

        plan["estimated_impact"] = self._estimate_impact(task, plan["steps"])
        return plan

    def _execute_plan(
        self,
        plan: dict[str, Any],
        files_modified: list[str],
    ) -> dict[str, Any]:
        """Phase 4: Execute the planned steps."""
        results: list[dict[str, Any]] = []
        for step in plan.get("steps", []):
            tool = step.get("tool", "")
            params = step.get("params", {})

            try:
                if tool == "read":
                    result = self._file_tool.read(params)
                elif tool == "create":
                    result = self._file_tool.create(params)
                    if result.get("success") and result.get("path"):
                        files_modified.append(result["path"])
                elif tool == "edit":
                    result = self._file_tool.edit(params)
                    if result.get("success") and result.get("path"):
                        files_modified.append(result["path"])
                elif tool == "delete":
                    result = self._file_tool.delete(params)
                    if result.get("success") and result.get("path"):
                        files_modified.append(result["path"])
                elif tool == "rename":
                    result = self._file_tool.rename(params)
                elif tool == "analyze":
                    result = self._code_analyzer.analyze(params)
                else:
                    result = {"success": False, "error": f"Unknown tool: {tool}"}
            except Exception as exc:
                result = {"success": False, "error": str(exc)}

            results.append(result)

        return {"steps": results, "success": all(r.get("success", False) for r in results)}

    def _verify(self, task: str, execution_result: dict[str, Any]) -> dict[str, Any]:
        """Phase 5: Verify that the execution was successful."""
        if execution_result.get("success", False):
            return {"success": True, "error": None}

        errors = [
            r.get("error", "Unknown error") for r in execution_result.get("steps", []) if not r.get("success", False)
        ]
        return {
            "success": False,
            "error": "; ".join(errors) if errors else "Execution failed",
        }

    def _retry(
        self,
        task: str,
        old_plan: dict[str, Any],
        verification: dict[str, Any],
    ) -> dict[str, Any]:
        """Phase 6: Adjust plan based on verification results."""
        adjusted = dict(old_plan)
        for step in adjusted.get("steps", []):
            if step.get("tool") == "read" and verification.get("error"):
                step["params"]["retry"] = True
        return adjusted

    def _report(
        self,
        task: str,
        errors: list[str],
        files_modified: list[str],
        phase_results: dict[str, Any],
    ) -> str:
        """Phase 7: Produce a final report."""
        lines = [
            f"Task: {task}",
            f"Files modified: {len(files_modified)}",
            f"Errors: {len(errors)}",
        ]
        if files_modified:
            lines.append("Modified files:")
            for f in files_modified:
                lines.append(f"  - {f}")
        if errors:
            lines.append("Errors encountered:")
            for e in errors:
                lines.append(f"  - {e}")
        return "\n".join(lines)

    # ── Analysis helpers ────────────────────────────────────────────────────────

    def _estimate_complexity(self, task: str) -> str:
        task_lower = task.lower()
        if any(kw in task_lower for kw in ["refactor", "redesign", "migrate", "restructure"]):
            return "high"
        if any(kw in task_lower for kw in ["add", "implement", "create", "build"]):
            return "medium"
        return "low"

    def _detect_required_tools(self, task: str) -> list[str]:
        tools: list[str] = []
        task_lower = task.lower()

        if any(kw in task_lower for kw in ["read", "show", "display", "what", "list"]):
            tools.append("read")
        if any(kw in task_lower for kw in ["create", "new file", "write", "add"]):
            tools.append("create")
        if any(kw in task_lower for kw in ["edit", "change", "update", "modify", "fix"]):
            tools.append("edit")
        if any(kw in task_lower for kw in ["delete", "remove"]):
            tools.append("delete")
        if any(kw in task_lower for kw in ["rename", "move"]):
            tools.append("rename")
        if any(kw in task_lower for kw in ["analyze", "check", "review", "audit"]):
            tools.append("analyze")

        if not tools:
            tools.append("analyze")

        return tools

    def _assess_risks(self, task: str) -> list[str]:
        risks: list[str] = []
        task_lower = task.lower()
        if "delete" in task_lower:
            risks.append("File deletion — data loss possible")
        if "refactor" in task_lower:
            risks.append("Refactoring may break existing functionality")
        if "rename" in task_lower:
            risks.append("Renaming may break imports")
        return risks

    def _suggest_read_targets(self, task: str) -> dict[str, Any]:
        task_lower = task.lower()
        if "config" in task_lower:
            return {"path": "config/", "pattern": "*.py"}
        if "test" in task_lower:
            return {"path": "tests/", "pattern": "*.py"}
        if "model" in task_lower:
            return {"path": "models/", "pattern": "*.py"}
        if "service" in task_lower:
            return {"path": "services/", "pattern": "*.py"}
        if "ui" in task_lower:
            return {"path": "ui/", "pattern": "*.py"}
        return {"path": ".", "pattern": "*.py"}

    def _estimate_impact(self, task: str, steps: list[dict]) -> list[str]:
        impact: list[str] = []
        for step in steps:
            tool = step.get("tool", "")
            if tool in ("edit", "create", "delete", "rename"):
                impact.append(f"{tool}: {step.get('description', '')}")
        return impact
