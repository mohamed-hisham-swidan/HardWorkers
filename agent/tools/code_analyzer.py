"""Code analysis tool for the agent system.

Provides static analysis capabilities including:
- Import detection and dependency mapping
- Function/class extraction
- Code quality assessment
- Refactoring suggestions
"""

from __future__ import annotations

import ast
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger("hard_workers.agent.tools.code_analyzer")


class CodeAnalyzerTool:
    """Static code analysis for Python projects."""

    def analyze(self, params: dict[str, Any]) -> dict[str, Any]:
        """Analyze code in a file or directory."""
        path = params.get("path", ".")
        analysis_type = params.get("type", "full")

        target = Path(path)
        if not target.exists():
            return {"success": False, "error": f"Path not found: {target}"}

        if target.is_dir():
            return self._analyze_directory(target, analysis_type)
        elif target.suffix == ".py":
            return self._analyze_python_file(target, analysis_type)
        else:
            return {"success": False, "error": f"Unsupported file type: {target.suffix}"}

    def _analyze_directory(
        self,
        directory: Path,
        analysis_type: str,
    ) -> dict[str, Any]:
        results: dict[str, Any] = {
            "success": True,
            "path": str(directory),
            "type": "directory",
            "files": [],
            "summary": {},
        }

        py_files = list(directory.rglob("*.py"))
        total_issues = 0
        total_lines = 0
        imports: dict[str, list[str]] = {}

        for f in py_files:
            try:
                analysis = self._analyze_python_file(f, analysis_type)
                results["files"].append(analysis)
                total_lines += analysis.get("lines", 0)
                total_issues += len(analysis.get("issues", []))
                for imp in analysis.get("imports", []):
                    imports.setdefault(imp, []).append(str(f))
            except Exception as exc:
                results["files"].append({
                    "path": str(f),
                    "error": str(exc),
                })

        results["summary"] = {
            "total_files": len(py_files),
            "total_lines": total_lines,
            "total_issues": total_issues,
            "unique_imports": len(imports),
            "import_map": imports,
        }
        return results

    def _analyze_python_file(
        self,
        filepath: Path,
        analysis_type: str,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {
            "success": True,
            "path": str(filepath),
            "type": "file",
            "language": "python",
        }

        try:
            source = filepath.read_text(encoding="utf-8")
        except Exception as exc:
            return {"success": False, "path": str(filepath), "error": str(exc)}

        result["lines"] = source.count("\n") + 1
        result["size"] = len(source)

        try:
            tree = ast.parse(source, filename=str(filepath))

            result["imports"] = self._extract_imports(tree)
            result["classes"] = self._extract_classes(tree)
            result["functions"] = self._extract_functions(tree)
            result["issues"] = self._detect_issues(tree, source) if analysis_type in ("full", "issues") else []
            result["complexity"] = self._calculate_complexity(tree) if analysis_type in ("full", "complexity") else {}

        except SyntaxError as exc:
            result["error"] = f"Syntax error: {exc}"
            result["issues"] = [{"type": "syntax", "message": str(exc), "line": exc.lineno or 0}]

        return result

    def _extract_imports(self, tree: ast.AST) -> list[str]:
        imports: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.append(node.module)
        return sorted(set(imports))

    def _extract_classes(self, tree: ast.AST) -> list[dict[str, Any]]:
        classes: list[dict[str, Any]] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                bases = []
                for base in node.bases:
                    if isinstance(base, ast.Name):
                        bases.append(base.id)
                    elif isinstance(base, ast.Attribute):
                        bases.append(f"{base.value.id}.{base.attr}")
                methods = [
                    {"name": n.name, "lines": n.end_lineno - n.lineno + 1 if n.end_lineno else 0}
                    for n in node.body
                    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                ]
                classes.append({
                    "name": node.name,
                    "bases": bases,
                    "methods": methods,
                    "lines": (node.end_lineno or node.lineno) - node.lineno + 1,
                    "decorators": [self._decorator_name(d) for d in node.decorator_list],
                })
        return classes

    def _extract_functions(self, tree: ast.AST) -> list[dict[str, Any]]:
        functions: list[dict[str, Any]] = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                args = [arg.arg for arg in node.args.args]
                decorators = [self._decorator_name(d) for d in node.decorator_list]
                returns = None
                if node.returns:
                    returns = ast.dump(node.returns)
                functions.append({
                    "name": node.name,
                    "args": args,
                    "decorators": decorators,
                    "returns": returns,
                    "lines": (node.end_lineno or node.lineno) - node.lineno + 1,
                })
        return functions

    def _detect_issues(self, tree: ast.AST, source: str) -> list[dict[str, Any]]:
        issues: list[dict[str, Any]] = []

        for node in ast.walk(tree):
            # Functions without docstrings
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if not ast.get_docstring(node):
                    issues.append({
                        "type": "style",
                        "message": "Missing docstring",
                        "line": node.lineno,
                        "name": node.name,
                    })
                # Function too long
                func_lines = (node.end_lineno or node.lineno) - node.lineno
                if func_lines > 50:
                    issues.append({
                        "type": "complexity",
                        "message": f"Function too long ({func_lines} lines)",
                        "line": node.lineno,
                        "name": node.name,
                    })

            # Bare except clauses
            if isinstance(node, ast.ExceptHandler) and node.type is None:
                issues.append({
                    "type": "security",
                    "message": "Bare except clause",
                    "line": node.lineno,
                })

            # Too many branches
            if isinstance(node, ast.FunctionDef):
                branches = sum(1 for _ in ast.walk(node) if isinstance(_, (ast.If, ast.For, ast.While)))
                if branches > 10:
                    issues.append({
                        "type": "complexity",
                        "message": f"Too many branches ({branches})",
                        "line": node.lineno,
                        "name": node.name,
                    })

        # Check for print statements
        for i, line in enumerate(source.split("\n"), 1):
            stripped = line.strip()
            if stripped.startswith("print(") and "logging" not in source:
                issues.append({
                    "type": "style",
                    "message": "Print statement detected — use logging instead",
                    "line": i,
                })

        return issues

    def _calculate_complexity(self, tree: ast.AST) -> dict[str, Any]:
        """Calculate cyclomatic complexity metrics."""
        complexity: dict[str, Any] = {
            "total_functions": 0,
            "total_classes": 0,
            "average_function_length": 0,
            "max_function_length": 0,
        }
        func_lengths: list[int] = []

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                complexity["total_functions"] += 1
                flen = (node.end_lineno or node.lineno) - node.lineno
                func_lengths.append(flen)
            elif isinstance(node, ast.ClassDef):
                complexity["total_classes"] += 1

        if func_lengths:
            complexity["average_function_length"] = sum(func_lengths) / len(func_lengths)
            complexity["max_function_length"] = max(func_lengths)

        return complexity

    @staticmethod
    def _decorator_name(node: ast.AST) -> str:
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return f"{node.value.id}.{node.attr}" if hasattr(node.value, "id") else ast.dump(node)
        elif isinstance(node, ast.Call):
            return CodeAnalyzerTool._decorator_name(node.func)
        return ast.dump(node)
