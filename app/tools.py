from __future__ import annotations

import difflib
import json
import shlex
import subprocess
from pathlib import Path
from typing import Any


class ToolError(RuntimeError):
    pass


class SafeTools:
    SAFE_COMMANDS = {"pwd", "ls", "cat", "head", "tail", "find", "rg", "sed", "wc"}

    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace.resolve()

    def run(self, tool_name: str, args: dict[str, Any], permission_level: str = "none") -> dict[str, Any]:
        if permission_level == "none":
            raise ToolError("Tool execution is disabled.")
        if tool_name in {"write_file", "patch_file"} and permission_level != "write":
            raise ToolError("This tool requires write permission.")
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

    def _resolve(self, rel_path: str) -> Path:
        candidate = (self.workspace / rel_path).resolve()
        if self.workspace not in candidate.parents and candidate != self.workspace:
            raise ToolError("Path escapes the workspace.")
        return candidate


def format_tool_result(result: dict[str, Any]) -> str:
    return json.dumps(result, ensure_ascii=False, indent=2)
