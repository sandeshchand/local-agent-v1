from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TEXT_SUFFIXES = {
    ".cfg",
    ".csv",
    ".env.example",
    ".ini",
    ".json",
    ".log",
    ".md",
    ".py",
    ".ps1",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}

SENSITIVE_FILE_NAMES = {
    ".env",
    "credentials",
    "credentials.json",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
    "id_rsa",
    "secrets.json",
}

SENSITIVE_SUFFIXES = {
    ".key",
    ".p12",
    ".pem",
    ".pfx",
}


class ReadOnlyFileMCPClient:
    """Small read-only file client that exposes MCP-style file tools."""

    def __init__(
        self,
        allowed_roots: list[Path],
        *,
        base_dir: Path,
        max_read_bytes: int = 20000,
    ) -> None:
        self.base_dir = base_dir.resolve()
        self.allowed_roots = [root.resolve() for root in allowed_roots]
        self.max_read_bytes = max(1000, min(max_read_bytes, 50000))

    def list_tools(self) -> dict[str, list[dict[str, Any]]]:
        read_only = {"readOnlyHint": True}
        return {
            "tools": [
                {
                    "name": "list_directory",
                    "description": "List files in an allowed read-only local directory.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string"},
                            "max_entries": {"type": "integer"},
                        },
                    },
                    "annotations": read_only,
                },
                {
                    "name": "read_text_file",
                    "description": "Read a UTF-8 text file from an allowed local path.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string"},
                            "max_bytes": {"type": "integer"},
                        },
                        "required": ["path"],
                    },
                    "annotations": read_only,
                },
                {
                    "name": "file_info",
                    "description": "Return metadata for an allowed local file or directory.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {"path": {"type": "string"}},
                        "required": ["path"],
                    },
                    "annotations": read_only,
                },
            ]
        }

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            if name == "list_directory":
                return self.list_directory(
                    path=str(arguments.get("path") or ""),
                    max_entries=_as_int(arguments.get("max_entries"), default=100, upper=500),
                )
            if name == "read_text_file":
                return self.read_text_file(
                    path=str(arguments.get("path") or ""),
                    max_bytes=_as_int(arguments.get("max_bytes"), default=self.max_read_bytes, upper=50000),
                )
            if name == "file_info":
                return self.file_info(path=str(arguments.get("path") or ""))
        except PermissionError as exc:
            return {
                "tool": name,
                "success": False,
                "path": str(arguments.get("path") or ""),
                "error": str(exc),
            }
        return {
            "success": False,
            "error": f"Unknown read-only file tool '{name}'.",
        }

    def list_directory(self, path: str = "", max_entries: int = 100) -> dict[str, Any]:
        if not path.strip():
            return {
                "tool": "list_directory",
                "success": True,
                "path": "",
                "entries": [self._root_entry(root) for root in self.allowed_roots],
                "root_listing": True,
            }

        directory = self._resolve_allowed(path)
        if not directory.exists():
            return self._failure("list_directory", path, "Path does not exist.")
        if not directory.is_dir():
            return self._failure("list_directory", path, "Path is not a directory.")

        entries = []
        for child in sorted(directory.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower())):
            if child.name.startswith("."):
                continue
            entries.append(self._path_entry(child))
            if len(entries) >= max_entries:
                break

        return {
            "tool": "list_directory",
            "success": True,
            "path": self._display_path(directory),
            "entries": entries,
            "truncated": len(entries) >= max_entries,
        }

    def read_text_file(self, path: str, max_bytes: int | None = None) -> dict[str, Any]:
        target = self._resolve_allowed(path)
        if not target.exists():
            return self._failure("read_text_file", path, "Path does not exist.")
        if not target.is_file():
            return self._failure("read_text_file", path, "Path is not a file.")
        if self._is_sensitive_path(target):
            return self._failure("read_text_file", path, "Hidden or sensitive files are not readable.")
        if not self._is_text_file(target):
            return self._failure("read_text_file", path, "Only text-like files are readable through this tool.")

        limit = max(1000, min(max_bytes or self.max_read_bytes, 50000))
        raw = target.read_bytes()
        content_bytes = raw[:limit]
        content = content_bytes.decode("utf-8", errors="replace")

        return {
            "tool": "read_text_file",
            "success": True,
            "path": self._display_path(target),
            "size_bytes": len(raw),
            "returned_bytes": len(content_bytes),
            "truncated": len(raw) > len(content_bytes),
            "content": content,
        }

    def file_info(self, path: str) -> dict[str, Any]:
        target = self._resolve_allowed(path)
        if not target.exists():
            return self._failure("file_info", path, "Path does not exist.")
        if self._is_sensitive_path(target):
            return self._failure("file_info", path, "Hidden or sensitive files are not accessible.")

        stat = target.stat()
        return {
            "tool": "file_info",
            "success": True,
            "path": self._display_path(target),
            "is_dir": target.is_dir(),
            "is_file": target.is_file(),
            "size_bytes": stat.st_size,
            "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        }

    def _resolve_allowed(self, path: str) -> Path:
        raw_path = Path(path.strip()).expanduser()
        candidate = raw_path if raw_path.is_absolute() else self.base_dir / raw_path
        resolved = candidate.resolve()
        if not self._is_allowed(resolved):
            allowed = ", ".join(self._display_path(root) for root in self.allowed_roots)
            raise PermissionError(f"Path is outside allowed File MCP roots: {allowed}")
        return resolved

    def _is_allowed(self, path: Path) -> bool:
        for root in self.allowed_roots:
            if path == root:
                return True
            if root.is_dir() and root in path.parents:
                return True
        return False

    def _is_text_file(self, path: Path) -> bool:
        suffix = path.suffix.lower()
        if suffix in TEXT_SUFFIXES:
            return True
        if path.name.lower().endswith(".env.example"):
            return True
        return suffix == "" and path.stat().st_size <= self.max_read_bytes

    def _is_sensitive_path(self, path: Path) -> bool:
        lower_name = path.name.lower()
        if lower_name.endswith(".env.example"):
            return False
        if any(part.startswith(".") for part in path.parts):
            return True
        if lower_name in SENSITIVE_FILE_NAMES:
            return True
        return path.suffix.lower() in SENSITIVE_SUFFIXES

    def _root_entry(self, root: Path) -> dict[str, Any]:
        return {
            "name": self._display_path(root),
            "path": self._display_path(root),
            "type": "directory" if root.is_dir() else "file",
            "exists": root.exists(),
        }

    def _path_entry(self, path: Path) -> dict[str, Any]:
        return {
            "name": path.name,
            "path": self._display_path(path),
            "type": "directory" if path.is_dir() else "file",
            "size_bytes": path.stat().st_size if path.is_file() else None,
        }

    def _display_path(self, path: Path) -> str:
        try:
            return path.resolve().relative_to(self.base_dir).as_posix()
        except ValueError:
            return str(path)

    def _failure(self, tool: str, path: str, error: str) -> dict[str, Any]:
        return {
            "tool": tool,
            "success": False,
            "path": path,
            "error": error,
        }


def _as_int(value: Any, *, default: int, upper: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, min(parsed, upper))
