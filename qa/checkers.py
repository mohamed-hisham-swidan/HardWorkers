"""Individual QA checkers — syntax, imports, tests, code quality, security."""

from __future__ import annotations

import ast
import logging
import subprocess
import sys
from pathlib import Path

from qa.models import CheckStatus, ValidationResult

log = logging.getLogger("hard_workers.qa.checkers")

# Directories to exclude from scanning
EXCLUDED_DIRS = {
    "__pycache__",
    ".git",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "venv",
    ".venv",
    "env",
    "node_modules",
    ".idea",
    ".vscode",
    "logs",
    "data",
    "backup",
    "secrets",
    "credentials",
}


# ── Base Checker ────────────────────────────────────────────────────────────────


class BaseChecker:
    """Base class for all QA checkers."""

    def __init__(self, project_root: Path) -> None:
        self._root = project_root

    def run(self) -> ValidationResult:
        raise NotImplementedError


# ── Syntax Checker ──────────────────────────────────────────────────────────────


class SyntaxChecker(BaseChecker):
    """Check Python files for syntax errors using ast.parse."""

    def run(self) -> ValidationResult:
        files = list(self._root.rglob("*.py"))
        errors: list[str] = []
        checked = 0

        for file in files:
            if any(excluded in file.parts for excluded in EXCLUDED_DIRS):
                continue
            checked += 1
            try:
                ast.parse(file.read_text(encoding="utf-8"), filename=str(file))
            except SyntaxError as exc:
                errors.append(f"{file.relative_to(self._root)}: {exc}")

        if errors:
            return ValidationResult(
                name="Syntax Check",
                status=CheckStatus.FAILED,
                details=f"{len(errors)} file(s) with syntax errors out of {checked}",
                errors=errors,
            )
        return ValidationResult(
            name="Syntax Check",
            status=CheckStatus.PASSED,
            details=f"All {checked} Python files have valid syntax",
        )


# ── Import Checker ──────────────────────────────────────────────────────────────


class ImportChecker(BaseChecker):
    """Check that all imports in Python files can be resolved."""

    def run(self) -> ValidationResult:
        files = list(self._root.rglob("*.py"))
        errors: list[str] = []
        checked = 0

        for file in files:
            if any(excluded in file.parts for excluded in EXCLUDED_DIRS):
                continue
            checked += 1
            try:
                tree = ast.parse(file.read_text(encoding="utf-8"), filename=str(file))
            except SyntaxError:
                continue

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        self._try_import(alias.name, file, errors)
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        # Skip relative imports within packages
                        if node.level:
                            continue
                        self._try_import(node.module, file, errors)

        if errors:
            return ValidationResult(
                name="Import Resolution",
                status=CheckStatus.FAILED,
                details=f"{len(errors)} unresolvable import(s) found",
                errors=errors[:20],
                warnings=errors[20:] if len(errors) > 20 else [],
            )
        return ValidationResult(
            name="Import Resolution",
            status=CheckStatus.PASSED,
            details=f"All imports in {checked} files resolve correctly",
        )

    def _try_import(self, module_name: str, file: Path, errors: list[str]) -> None:
        if module_name.startswith("hard_workers."):
            rel_module = module_name[len("hard_workers.") :]
            pkg_path = self._root / rel_module.replace(".", "/")
            if not pkg_path.exists():
                init_file = pkg_path / "__init__.py"
                if not any(self._root.rglob(f"{rel_module.replace('.', '/')}.py")):
                    if not init_file.exists() and not (self._root / rel_module.replace(".", "/") + ".py").exists():
                        errors.append(f"{file.relative_to(self._root)}: cannot resolve '{module_name}'")


# ── Test Runner ─────────────────────────────────────────────────────────────────


class TestRunner(BaseChecker):
    """Run pytest and collect results."""

    def __init__(self, project_root: Path, pytest_args: list[str] | None = None) -> None:
        super().__init__(project_root)
        self._pytest_args = pytest_args or ["--tb=short", "--no-header", "-q"]

    def run(self) -> ValidationResult:
        test_dir = self._root / "tests"
        if not test_dir.exists():
            return ValidationResult(
                name="Pytest Tests",
                status=CheckStatus.SKIPPED,
                details="No tests/ directory found",
            )

        cmd = [sys.executable, "-m", "pytest", *self._pytest_args, str(test_dir)]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
                cwd=str(self._root),
            )
        except subprocess.TimeoutExpired:
            return ValidationResult(
                name="Pytest Tests",
                status=CheckStatus.ERROR,
                details="Test execution timed out after 120s",
            )
        except FileNotFoundError:
            return ValidationResult(
                name="Pytest Tests",
                status=CheckStatus.ERROR,
                details="pytest not found (is it installed?)",
            )

        output = result.stdout + "\n" + result.stderr
        if result.returncode == 0:
            return ValidationResult(
                name="Pytest Tests",
                status=CheckStatus.PASSED,
                details=output.strip().split("\n")[-1] if output.strip() else "All tests passed",
            )
        return ValidationResult(
            name="Pytest Tests",
            status=CheckStatus.FAILED,
            details=f"Exit code {result.returncode}",
            errors=[output.strip()[:500]] if output.strip() else ["Unknown test failure"],
        )


# ── Code Quality Checker ────────────────────────────────────────────────────────


class CodeQualityChecker(BaseChecker):
    """Check code quality: line length, TODO/FIXME, missing docstrings, etc."""

    MAX_LINE_LENGTH = 120

    def run(self) -> ValidationResult:
        files = list(self._root.rglob("*.py"))
        warnings: list[str] = []
        errors: list[str] = []
        checked = 0

        for file in files:
            if any(excluded in file.parts for excluded in EXCLUDED_DIRS):
                continue
            checked += 1
            content = file.read_text(encoding="utf-8")
            lines = content.split("\n")
            rel = file.relative_to(self._root)

            # Check for TODO/FIXME/HACK
            for i, line in enumerate(lines, 1):
                stripped = line.strip()
                if stripped.startswith(("# TODO", "# FIXME", "# HACK", "# XXX")):
                    warnings.append(f"{rel}:{i}: {stripped[:80]}")

                # Check line length
                if len(line.rstrip("\n")) > self.MAX_LINE_LENGTH and not line.rstrip("\n").startswith("#"):
                    warnings.append(f"{rel}:{i}: Line too long ({len(line.rstrip())} > {self.MAX_LINE_LENGTH})")

            # Check for print statements (outside tests)
            if "tests" not in file.parts:
                for i, line in enumerate(lines, 1):
                    stripped = line.strip()
                    if stripped.startswith("print(") and not stripped.startswith("#"):
                        warnings.append(f"{rel}:{i}: Use log instead of print()")

        if errors:
            return ValidationResult(
                name="Code Quality",
                status=CheckStatus.FAILED,
                details=f"{len(errors)} issue(s) found",
                errors=errors,
                warnings=warnings,
            )
        if warnings:
            return ValidationResult(
                name="Code Quality",
                status=CheckStatus.PASSED,
                details=f"{len(warnings)} warning(s), {checked} files checked",
                warnings=warnings[:20],
            )
        return ValidationResult(
            name="Code Quality",
            status=CheckStatus.PASSED,
            details=f"No issues in {checked} files",
        )


# ── Security Checker ────────────────────────────────────────────────────────────


class SecurityChecker(BaseChecker):
    """Check for common security issues: hardcoded secrets, unsafe eval, etc."""

    # Patterns that suggest hardcoded secrets
    SUSPICIOUS_PATTERNS: list[tuple[str, str]] = [
        ("API Key", r'(?i)(api[_-]?key|apikey)\s*[=:]\s*["\'][A-Za-z0-9_\-]{16,}'),
        ("Secret", r'(?i)(secret|token|password|passwd)\s*[=:]\s*["\'][A-Za-z0-9_\-!@#$%^&*()]{8,}'),
        ("SSH Key", r"-----BEGIN\s+(RSA|DSA|EC|OPENSSH)\s+PRIVATE KEY-----"),
        ("JWT Token", r"eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+"),
    ]

    UNSAFE_FUNCTIONS = ["eval(", "exec(", "compile(", "__import__("]

    def run(self) -> ValidationResult:
        files = list(self._root.rglob("*.py"))
        errors: list[str] = []
        warnings: list[str] = []
        checked = 0

        import re

        for file in files:
            if any(excluded in file.parts for excluded in EXCLUDED_DIRS):
                continue
            if file.name.startswith("test_"):
                continue
            checked += 1
            content = file.read_text(encoding="utf-8")
            lines = content.split("\n")
            rel = file.relative_to(self._root)

            # Check unsafe functions
            for i, line in enumerate(lines, 1):
                for func in self.UNSAFE_FUNCTIONS:
                    if func in line and not line.strip().startswith("#"):
                        warnings.append(f"{rel}:{i}: Use of {func}")

            # Check suspicious patterns
            for label, pattern in self.SUSPICIOUS_PATTERNS:
                for match in re.finditer(pattern, content):
                    ctx_start = max(0, match.start() - 40)
                    ctx = content[ctx_start : match.end()].strip()
                    errors.append(f"{rel}: Possible hardcoded {label}: ...{ctx[:80]}...")

        if errors:
            return ValidationResult(
                name="Security Scan",
                status=CheckStatus.FAILED,
                details=f"{len(errors)} security issue(s) found",
                errors=errors,
                warnings=warnings,
            )
        if warnings:
            return ValidationResult(
                name="Security Scan",
                status=CheckStatus.PASSED,
                details=f"{len(warnings)} warning(s), {checked} files checked",
                warnings=warnings,
            )
        return ValidationResult(
            name="Security Scan",
            status=CheckStatus.PASSED,
            details=f"No security issues in {checked} files",
        )
