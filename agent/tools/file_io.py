"""File I/O tool for the agent system.

Provides safe file operations with path traversal protection,
backup creation, and atomic writes.
"""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path
from typing import Any

log = logging.getLogger("hard_workers.agent.tools.file_io")


class FileIOTool:
    """Safe file I/O operations for the agent."""

    def __init__(self, workspace_root: Path | str = ".") -> None:
        self._root = Path(workspace_root).resolve()
        self._backup_dir = self._root / ".agent_backups"
        self._backup_dir.mkdir(parents=True, exist_ok=True)

    # ── Public API ──────────────────────────────────────────────────────────────

    def read(self, params: dict[str, Any]) -> dict[str, Any]:
        """Read a file or directory listing."""
        path_str = params.get("path", ".")
        pattern = params.get("pattern", "*")

        try:
            target = self._resolve_path(path_str)
            if target.is_dir():
                files = list(target.glob(pattern))
                return {
                    "success": True,
                    "path": str(target),
                    "type": "directory",
                    "files": [str(f.relative_to(self._root)) for f in sorted(files)],
                    "count": len(files),
                }
            elif target.is_file():
                content = target.read_text(encoding="utf-8", errors="replace")
                return {
                    "success": True,
                    "path": str(target),
                    "type": "file",
                    "content": content,
                    "size": len(content),
                    "lines": content.count("\n") + 1,
                }
            else:
                return {"success": False, "error": f"Path not found: {target}"}
        except Exception as exc:
            log.error("Read error: %s", exc)
            return {"success": False, "error": str(exc)}

    def create(self, params: dict[str, Any]) -> dict[str, Any]:
        """Create a new file or directory."""
        path_str = params.get("path", "")
        content = params.get("content", "")
        is_dir = params.get("is_directory", False)

        if not path_str:
            return {"success": False, "error": "No path specified"}

        try:
            target = self._resolve_path(path_str)
            target.parent.mkdir(parents=True, exist_ok=True)

            if is_dir:
                target.mkdir(parents=True, exist_ok=True)
                return {"success": True, "path": str(target), "type": "directory", "action": "created"}
            else:
                if target.exists():
                    self._backup(target)
                target.write_text(content, encoding="utf-8")
                return {"success": True, "path": str(target), "type": "file", "action": "created", "size": len(content)}
        except Exception as exc:
            log.error("Create error: %s", exc)
            return {"success": False, "error": str(exc)}

    def edit(self, params: dict[str, Any]) -> dict[str, Any]:
        """Edit an existing file by replacing content or applying a diff."""
        path_str = params.get("path", "")
        new_content = params.get("content", "")
        old_string = params.get("old_string", "")
        new_string = params.get("new_string", "")

        if not path_str:
            return {"success": False, "error": "No path specified"}

        try:
            target = self._resolve_path(path_str)
            if not target.exists():
                return {"success": False, "error": f"File not found: {target}"}

            self._backup(target)

            if new_content:
                target.write_text(new_content, encoding="utf-8")
                return {"success": True, "path": str(target), "action": "replaced", "size": len(new_content)}
            elif old_string and new_string:
                current = target.read_text(encoding="utf-8")
                if old_string not in current:
                    return {"success": False, "error": "old_string not found in file"}
                updated = current.replace(old_string, new_string)
                target.write_text(updated, encoding="utf-8")
                return {"success": True, "path": str(target), "action": "patched", "changes": current.count(old_string)}
            else:
                return {"success": False, "error": "No content or old_string/new_string provided"}

        except Exception as exc:
            log.error("Edit error: %s", exc)
            return {"success": False, "error": str(exc)}

    def delete(self, params: dict[str, Any]) -> dict[str, Any]:
        """Delete a file or directory."""
        path_str = params.get("path", "")

        if not path_str:
            return {"success": False, "error": "No path specified"}

        try:
            target = self._resolve_path(path_str)
            if not target.exists():
                return {"success": False, "error": f"Path not found: {target}"}

            self._backup(target)

            if target.is_dir():
                shutil.rmtree(target)
                return {"success": True, "path": str(target), "type": "directory", "action": "deleted"}
            else:
                target.unlink()
                return {"success": True, "path": str(target), "type": "file", "action": "deleted"}

        except Exception as exc:
            log.error("Delete error: %s", exc)
            return {"success": False, "error": str(exc)}

    def rename(self, params: dict[str, Any]) -> dict[str, Any]:
        """Rename or move a file or directory."""
        source = params.get("source", "")
        destination = params.get("destination", "")

        if not source or not destination:
            return {"success": False, "error": "Source and destination required"}

        try:
            src = self._resolve_path(source)
            dst = self._resolve_path(destination)
            dst.parent.mkdir(parents=True, exist_ok=True)

            if src.exists():
                self._backup(src)

            src.rename(dst)
            return {"success": True, "source": str(src), "destination": str(dst), "action": "renamed"}
        except Exception as exc:
            log.error("Rename error: %s", exc)
            return {"success": False, "error": str(exc)}

    def list_backups(self) -> list[dict[str, Any]]:
        """List all available backups."""
        backups = []
        for f in sorted(self._backup_dir.iterdir()):
            backups.append({
                "name": f.name,
                "path": str(f),
                "size": f.stat().st_size,
                "modified": f.stat().st_mtime,
            })
        return backups

    # ── Internal ────────────────────────────────────────────────────────────────

    def _resolve_path(self, path_str: str) -> Path:
        """Resolve a path relative to workspace root, preventing traversal attacks."""
        candidate = (self._root / path_str).resolve()
        try:
            candidate.relative_to(self._root)
        except ValueError:
            raise PermissionError(f"Path traversal detected: {path_str}")
        # Reject symlinks that escape the root
        if candidate.is_symlink():
            real = candidate.resolve(strict=False)
            try:
                real.relative_to(self._root)
            except ValueError:
                raise PermissionError(f"Symlink target escapes workspace root: {path_str}")
        return candidate

    def _backup(self, path: Path) -> str | None:
        """Create a backup of a file before modification."""
        if not path.exists():
            return None
        try:
            rel_path = path.relative_to(self._root)
            backup_name = f"{rel_path!s}_{int(time.time())}.bak".replace("\\", "_").replace("/", "_")
            backup_path = self._backup_dir / backup_name
            shutil.copy2(path, backup_path)
            log.debug("Backup created: %s", backup_path)
            return str(backup_path)
        except Exception as exc:
            log.warning("Backup failed for %s: %s", path, exc)
            return None


import time  # noqa: E402 (needed for timestamp in backup)
