from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .templates import TemplateManager


STACK_TEMPLATES = {
    "fastapi": "fastapi-api",
    "flask": "flask-api",
    "node": "node-api",
    "react": "react-starter",
    "web": "web-starter",
    "python": "python-api",
}


@dataclass(frozen=True)
class BuildPlan:
    stack: str
    template_id: str
    install_commands: list[str]
    run_commands: list[str]
    test_commands: list[str]
    folders: list[str]


class ProjectBuilder:
    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace.resolve()
        self.template_manager = TemplateManager(self.workspace)

    def build(
        self,
        description: str,
        target_dir: str,
        project_name: str | None = None,
        allow_external: bool = False,
    ) -> dict[str, Any]:
        build_root = self._resolve_target(target_dir, allow_external=allow_external)
        build_root.mkdir(parents=True, exist_ok=True)
        name = project_name or self._slugify(description) or build_root.name or "generated-project"
        plan = self._detect_plan(description)
        written = self.template_manager.apply(plan.template_id, str(build_root))
        spec = self._build_manifest(name=name, description=description, target_dir=str(build_root), plan=plan)
        spec_path = build_root / "project_spec.json"
        spec_path.write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
        todo_path = build_root / "NEXT_STEPS.md"
        todo_path.write_text(self._next_steps_markdown(spec), encoding="utf-8")
        all_written = written + [self._relative_or_absolute(spec_path), self._relative_or_absolute(todo_path)]
        return {
            "project_name": name,
            "target_dir": str(build_root),
            "stack": plan.stack,
            "template_id": plan.template_id,
            "written": all_written,
            "manifest": spec,
        }

    def _detect_plan(self, description: str) -> BuildPlan:
        lowered = description.lower()
        if any(token in lowered for token in ("fastapi", "uvicorn", "api python حديث", "api حديث")):
            return BuildPlan(
                stack="fastapi",
                template_id=STACK_TEMPLATES["fastapi"],
                install_commands=["pip install -r requirements.txt"],
                run_commands=["uvicorn main:app --reload"],
                test_commands=["curl http://127.0.0.1:8000/health"],
                folders=["app", "tests"],
            )
        if any(token in lowered for token in ("flask",)):
            return BuildPlan(
                stack="flask",
                template_id=STACK_TEMPLATES["flask"],
                install_commands=["pip install -r requirements.txt"],
                run_commands=["python3 app.py"],
                test_commands=["curl http://127.0.0.1:5000/health"],
                folders=["app", "tests"],
            )
        if any(token in lowered for token in ("react", "واجهة react", "frontend react")):
            return BuildPlan(
                stack="react",
                template_id=STACK_TEMPLATES["react"],
                install_commands=["npm install react react-dom"],
                run_commands=["python3 -m http.server 3000"],
                test_commands=["open http://127.0.0.1:3000"],
                folders=["src", "public"],
            )
        if any(token in lowered for token in ("node", "express", "javascript api")):
            return BuildPlan(
                stack="node",
                template_id=STACK_TEMPLATES["node"],
                install_commands=["npm install"],
                run_commands=["npm start"],
                test_commands=["curl http://127.0.0.1:3000/health"],
                folders=["src", "tests"],
            )
        if any(token in lowered for token in ("html", "css", "landing", "صفحة")):
            return BuildPlan(
                stack="web",
                template_id=STACK_TEMPLATES["web"],
                install_commands=[],
                run_commands=["python3 -m http.server 3000"],
                test_commands=["open http://127.0.0.1:3000"],
                folders=["assets"],
            )
        return BuildPlan(
            stack="python",
            template_id=STACK_TEMPLATES["python"],
            install_commands=[],
            run_commands=["python3 main.py"],
            test_commands=["curl http://127.0.0.1:8000/health"],
            folders=["app", "tests"],
        )

    def _build_manifest(self, name: str, description: str, target_dir: str, plan: BuildPlan) -> dict[str, Any]:
        return {
            "name": name,
            "description": description,
            "target_dir": target_dir,
            "stack": plan.stack,
            "template_id": plan.template_id,
            "folders": plan.folders,
            "install_commands": plan.install_commands,
            "run_commands": plan.run_commands,
            "test_commands": plan.test_commands,
            "status": "scaffolded",
        }

    def _next_steps_markdown(self, spec: dict[str, Any]) -> str:
        install = "\n".join(f"- `{cmd}`" for cmd in spec["install_commands"]) or "- No install step required."
        run = "\n".join(f"- `{cmd}`" for cmd in spec["run_commands"]) or "- No run command defined."
        tests = "\n".join(f"- `{cmd}`" for cmd in spec["test_commands"]) or "- No test command defined."
        return (
            f"# Next Steps\n\n"
            f"## Install\n{install}\n\n"
            f"## Run\n{run}\n\n"
            f"## Test\n{tests}\n"
        )

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

    def _relative_or_absolute(self, path: Path) -> str:
        try:
            return str(path.relative_to(self.workspace))
        except ValueError:
            return str(path)

    @staticmethod
    def _slugify(text: str) -> str:
        cleaned = re.sub(r"[^\w\u0600-\u06FF]+", "-", text.strip().lower()).strip("-")
        return cleaned[:60]
