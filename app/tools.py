from __future__ import annotations

import difflib
import json
import shlex
import subprocess
from pathlib import Path
from typing import Any

from .internet_client import InternetClient, InternetError


class ToolError(RuntimeError):
    pass


class SafeTools:
    SAFE_COMMANDS = {"pwd", "ls", "cat", "head", "tail", "find", "rg", "sed", "wc"}
    TOOL_SCHEMAS = [
        {
            "type": "function",
            "function": {
                "name": "shell",
                "description": "Run a safe read-only shell command inside the workspace.",
                "parameters": {
                    "type": "object",
                    "properties": {"command": {"type": "string"}},
                    "required": ["command"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": "Read a UTF-8 text file inside the workspace.",
                "parameters": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "write_file",
                "description": "Create or overwrite a UTF-8 text file inside the workspace.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "content": {"type": "string"},
                    },
                    "required": ["path", "content"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "patch_file",
                "description": "Replace the first occurrence of text inside a workspace file.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "find": {"type": "string"},
                        "replace": {"type": "string"},
                    },
                    "required": ["path", "find", "replace"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "search_workspace",
                "description": "Search for a keyword in workspace files.",
                "parameters": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "list_files",
                "description": "List files or folders inside the workspace.",
                "parameters": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "web_search",
                "description": "Search the public web and return ranked results with citations.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "limit": {"type": "integer"},
                    },
                    "required": ["query"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "fetch_url",
                "description": "Fetch and extract readable text from a web page.",
                "parameters": {
                    "type": "object",
                    "properties": {"url": {"type": "string"}},
                    "required": ["url"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "web_fetch",
                "description": "Fetch a web page with the same behavior as fetch_url.",
                "parameters": {
                    "type": "object",
                    "properties": {"url": {"type": "string"}},
                    "required": ["url"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "fetch_json",
                "description": "Fetch a JSON URL and return parsed JSON.",
                "parameters": {
                    "type": "object",
                    "properties": {"url": {"type": "string"}},
                    "required": ["url"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "download_file",
                "description": "Download a remote file into the downloads folder.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string"},
                        "filename": {"type": "string"},
                    },
                    "required": ["url"],
                },
            },
        },
    ]

    def __init__(
        self,
        workspace: Path,
        internet_client: InternetClient | None = None,
        internet_enabled: bool = True,
        telemetry_hook: Any | None = None,
        post_download_hook: Any | None = None,
    ) -> None:
        self.workspace = workspace.resolve()
        self.internet_client = internet_client
        self.internet_enabled = internet_enabled
        self.telemetry_hook = telemetry_hook
        self.post_download_hook = post_download_hook

    def run(self, tool_name: str, args: dict[str, Any], permission_level: str = "none") -> dict[str, Any]:
        normalized = self._normalize_permission(permission_level)
        if normalized == "none":
            raise ToolError("Tool execution is disabled.")
        if tool_name in {"read_file", "search_workspace", "list_files", "shell"} and not self._allows_local_read(normalized):
            raise ToolError("This tool requires local read permission.")
        if tool_name in {"write_file", "patch_file"} and not self._allows_local_write(normalized):
            raise ToolError("This tool requires write permission.")
        if tool_name in {"web_search", "fetch_url", "web_fetch", "fetch_json"} and not self._allows_internet_read(normalized):
            raise ToolError("This tool requires internet read permission.")
        if tool_name == "download_file" and not self._allows_internet_download(normalized):
            raise ToolError("This tool requires internet download permission.")
        if tool_name == "shell":
            return self.shell(str(args.get("command", "")))
        if tool_name == "read_file":
            return self.read_file(str(args.get("path", "")))
        if tool_name == "write_file":
            return self.write_file(str(args.get("path", "")), str(args.get("content", "")))
        if tool_name == "patch_file":
            return self.patch_file(
                str(args.get("path", "")),
                str(args.get("find", "")),
                str(args.get("replace", "")),
            )
        if tool_name == "search_workspace":
            return self.search_workspace(str(args.get("query", "")))
        if tool_name == "list_files":
            return self.list_files(str(args.get("path", ".")))
        if tool_name == "web_search":
            return self.web_search(str(args.get("query", "")), int(args.get("limit", 5)))
        if tool_name == "fetch_url":
            return self.fetch_url(str(args.get("url", "")))
        if tool_name == "web_fetch":
            return self.fetch_url(str(args.get("url", "")))
        if tool_name == "fetch_json":
            return self.fetch_json(str(args.get("url", "")))
        if tool_name == "download_file":
            return self.download_file(str(args.get("url", "")), args.get("filename"))
        raise ToolError(f"Unsupported tool: {tool_name}")

    def shell(self, command: str) -> dict[str, Any]:
        parts = shlex.split(command)
        if not parts:
            raise ToolError("Empty command.")
        if parts[0] not in self.SAFE_COMMANDS:
            raise ToolError(f"Command '{parts[0]}' is not allowed.")
        completed = subprocess.run(
            parts,
            cwd=self.workspace,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        return {
            "command": command,
            "exit_code": completed.returncode,
            "stdout": completed.stdout[:4000],
            "stderr": completed.stderr[:2000],
        }

    def read_file(self, rel_path: str) -> dict[str, Any]:
        path = self._resolve(rel_path)
        if not path.exists():
            raise ToolError("File not found.")
        return {"path": rel_path, "content": path.read_text(encoding="utf-8", errors="ignore")[:8000]}

    def write_file(self, rel_path: str, content: str) -> dict[str, Any]:
        path = self._resolve(rel_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return {"path": rel_path, "bytes_written": len(content.encode("utf-8"))}

    def patch_file(self, rel_path: str, find_text: str, replace_text: str) -> dict[str, Any]:
        path = self._resolve(rel_path)
        if not path.exists():
            raise ToolError("File not found.")
        original = path.read_text(encoding="utf-8", errors="ignore")
        if find_text not in original:
            raise ToolError("Target text was not found.")
        updated = original.replace(find_text, replace_text, 1)
        path.write_text(updated, encoding="utf-8")
        diff = "\n".join(
            difflib.unified_diff(
                original.splitlines(),
                updated.splitlines(),
                fromfile=f"a/{rel_path}",
                tofile=f"b/{rel_path}",
                lineterm="",
            )
        )
        return {"path": rel_path, "diff": diff[:8000]}

    def search_workspace(self, query: str) -> dict[str, Any]:
        if not query.strip():
            raise ToolError("Query is empty.")
        matches = []
        for path in self.workspace.rglob("*"):
            if not path.is_file():
                continue
            if ".agent" in path.parts:
                continue
            if path.suffix.lower() not in {".py", ".md", ".txt", ".js", ".ts", ".json", ".html", ".css"}:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            if query.lower() in text.lower():
                matches.append(str(path.relative_to(self.workspace)))
            if len(matches) >= 20:
                break
        return {"query": query, "matches": matches}

    def list_files(self, rel_path: str) -> dict[str, Any]:
        path = self._resolve(rel_path)
        if not path.exists():
            raise ToolError("Path not found.")
        if path.is_file():
            return {"path": rel_path, "entries": [rel_path]}
        entries = []
        for child in sorted(path.rglob("*")):
            if ".agent" in child.parts:
                continue
            entries.append(str(child.relative_to(self.workspace)))
            if len(entries) >= 200:
                break
        return {"path": rel_path, "entries": entries}

    def web_search(self, query: str, limit: int = 5) -> dict[str, Any]:
        self._require_internet()
        if not query.strip():
            raise ToolError("Query is empty.")
        try:
            result = self.internet_client.search_web(query, limit=limit) if self.internet_client else {}
        except InternetError as exc:
            raise ToolError(str(exc)) from exc
        self._record_telemetry(
            "internet_search",
            {
                "query": query,
                "provider_used": result.get("provider_used"),
                "fallback_used": result.get("fallback_used"),
                "count": len(result.get("results", [])),
            },
        )
        return result

    def fetch_url(self, url: str) -> dict[str, Any]:
        self._require_internet()
        try:
            result = self.internet_client.fetch_url(url) if self.internet_client else {}
        except InternetError as exc:
            raise ToolError(str(exc)) from exc
        self._record_telemetry(
            "internet_fetch_url",
            {
                "url": url,
                "status": result.get("status"),
                "content_type": result.get("content_type"),
                "provider_used": result.get("provider_used"),
                "fallback_used": result.get("fallback_used"),
            },
        )
        return result

    def fetch_json(self, url: str) -> dict[str, Any]:
        self._require_internet()
        try:
            result = self.internet_client.fetch_json(url) if self.internet_client else {}
        except InternetError as exc:
            raise ToolError(str(exc)) from exc
        self._record_telemetry("internet_fetch_json", {"url": url, "status": result.get("status")})
        return result

    def download_file(self, url: str, filename: str | None = None) -> dict[str, Any]:
        self._require_internet()
        try:
            result = self.internet_client.download_file(url, filename=filename) if self.internet_client else {}
        except InternetError as exc:
            raise ToolError(str(exc)) from exc
        self._record_telemetry("internet_download", result)
        if self.post_download_hook:
            self.post_download_hook(result)
        return result

    def _resolve(self, rel_path: str) -> Path:
        candidate = (self.workspace / rel_path).resolve()
        if self.workspace not in candidate.parents and candidate != self.workspace:
            raise ToolError("Path escapes the workspace.")
        return candidate

    def _require_internet(self) -> None:
        if not self.internet_enabled or not self.internet_client:
            raise ToolError("Internet access is disabled in the current configuration.")

    def _record_telemetry(self, kind: str, payload: dict[str, Any]) -> None:
        if self.telemetry_hook:
            self.telemetry_hook(kind, payload)

    @staticmethod
    def _normalize_permission(permission_level: str) -> str:
        mapping = {
            "read": "local-read",
            "write": "local-write",
        }
        return mapping.get(permission_level, permission_level)

    @staticmethod
    def _allows_local_read(permission_level: str) -> bool:
        return permission_level in {"auto", "local-read", "local-write", "full"}

    @staticmethod
    def _allows_local_write(permission_level: str) -> bool:
        return permission_level in {"local-write", "full"}

    @staticmethod
    def _allows_internet_read(permission_level: str) -> bool:
        return permission_level in {"auto", "internet-read", "internet-download", "full"}

    @staticmethod
    def _allows_internet_download(permission_level: str) -> bool:
        return permission_level in {"auto", "internet-download", "full"}

    @classmethod
    def tool_schemas(cls) -> list[dict[str, Any]]:
        return cls.TOOL_SCHEMAS


def format_tool_result(result: dict[str, Any]) -> str:
    return json.dumps(result, ensure_ascii=False, indent=2)
