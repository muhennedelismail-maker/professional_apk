from __future__ import annotations

import json
import shlex
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class ExecutionResult:
    step: str
    command: str
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int


class ProjectExecutor:
    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace.resolve()

    def execute(
        self,
        target_dir: str,
        actions: list[str],
        allow_external: bool = False,
    ) -> dict[str, Any]:
        project_dir = self._resolve_target(target_dir, allow_external=allow_external)
        manifest = self._load_manifest(project_dir)
        results: list[ExecutionResult] = []
        fix_notes: list[str] = []
        background_process: subprocess.Popen[str] | None = None
        background_command = ""

        for index, action in enumerate(actions):
            commands = self._commands_for_action(action, manifest)
            if not commands:
                continue
            for command in commands:
                if action == "run":
                    next_actions = actions[index + 1 :]
                    background_process, run_result = self._start_background(command, cwd=project_dir)
                    background_command = command
                    results.append(run_result)
                    if run_result.exit_code != 0:
                        fix_notes.extend(self._auto_fix(project_dir, manifest, run_result))
                        return {
                            "target_dir": str(project_dir),
                            "manifest": manifest,
                            "results": [self._serialize(item) for item in results],
                            "fix_notes": fix_notes,
                            "status": "failed",
                        }
                    if not any(item in {"smoke", "test"} for item in next_actions):
                        self._stop_background(background_process)
                    continue
                result = self._run(command, cwd=project_dir)
                results.append(result)
                if result.exit_code != 0:
                    self._stop_background(background_process)
                    fix_notes.extend(self._auto_fix(project_dir, manifest, result))
                    return {
                        "target_dir": str(project_dir),
                        "manifest": manifest,
                        "results": [self._serialize(item) for item in results],
                        "fix_notes": fix_notes,
                        "status": "failed",
                    }

        self._stop_background(background_process)
        return {
            "target_dir": str(project_dir),
            "manifest": manifest,
            "results": [self._serialize(item) for item in results],
            "fix_notes": fix_notes,
            "status": "completed",
        }

    def _load_manifest(self, project_dir: Path) -> dict[str, Any]:
        manifest_path = project_dir / "project_spec.json"
        if not manifest_path.exists():
            raise ValueError("project_spec.json was not found in the target directory.")
        return json.loads(manifest_path.read_text(encoding="utf-8"))

    def _commands_for_action(self, action: str, manifest: dict[str, Any]) -> list[str]:
        if action == "install":
            return list(manifest.get("install_commands") or [])
        if action == "run":
            return list(manifest.get("run_commands") or [])
        if action == "test":
            return list(manifest.get("test_commands") or [])
        if action == "smoke":
            return list(manifest.get("test_commands") or [])
        return []

    def _run(self, command: str, cwd: Path) -> ExecutionResult:
        start = time.time()
        parts = shlex.split(command)
        completed = subprocess.run(
            parts,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        return ExecutionResult(
            step=parts[0],
            command=command,
            exit_code=completed.returncode,
            stdout=completed.stdout[:4000],
            stderr=completed.stderr[:4000],
            duration_ms=int((time.time() - start) * 1000),
        )

    def _start_background(self, command: str, cwd: Path) -> tuple[subprocess.Popen[str], ExecutionResult]:
        start = time.time()
        process = subprocess.Popen(
            shlex.split(command),
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        time.sleep(2)
        exit_code = process.poll()
        stdout = ""
        stderr = ""
        if exit_code is not None:
            stdout, stderr = process.communicate(timeout=1)
        result = ExecutionResult(
            step="run",
            command=command,
            exit_code=0 if exit_code is None else exit_code,
            stdout=stdout[:4000],
            stderr=stderr[:4000],
            duration_ms=int((time.time() - start) * 1000),
        )
        return process, result

    def _stop_background(self, process: subprocess.Popen[str] | None) -> None:
        if not process:
            return
        if process.poll() is not None:
            if process.stdout:
                process.stdout.close()
            if process.stderr:
                process.stderr.close()
            return
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
        if process.stdout:
            process.stdout.close()
        if process.stderr:
            process.stderr.close()

    def _auto_fix(self, project_dir: Path, manifest: dict[str, Any], result: ExecutionResult) -> list[str]:
        notes: list[str] = []
        stderr = result.stderr.lower()
        if "no such file or directory" in stderr:
            notes.append("Check the generated file paths and make sure the scaffold wrote the expected entry file.")
        if "no module named" in stderr or "command not found" in stderr:
            notes.append("A dependency appears to be missing. Run the install commands from project_spec.json first.")
        if "address already in use" in stderr:
            notes.append("The selected port is busy. Change the run port or stop the conflicting process.")
        fix_path = project_dir / "AUTO_FIX_NOTES.md"
        if notes:
            fix_path.write_text(
                "# Auto Fix Notes\n\n" + "\n".join(f"- {note}" for note in notes) + "\n",
                encoding="utf-8",
            )
            notes.append(f"Generated {fix_path.name} with first-pass remediation notes.")
        return notes

    def _resolve_target(self, target_dir: str, allow_external: bool) -> Path:
        candidate = Path(target_dir).expanduser()
        if not candidate.is_absolute():
            candidate = self.workspace / candidate
        resolved = candidate.resolve()
        if allow_external:
            return resolved
        try:
            resolved.relative_to(self.workspace)
        except ValueError as exc:
            raise ValueError("Target directory must stay inside the workspace unless external access is allowed.") from exc
        return resolved

    @staticmethod
    def _serialize(result: ExecutionResult) -> dict[str, Any]:
        return {
            "step": result.step,
            "command": result.command,
            "exit_code": result.exit_code,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "duration_ms": result.duration_ms,
        }
