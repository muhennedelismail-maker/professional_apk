from __future__ import annotations

import base64
import json
import re
import time
import uuid
from pathlib import Path
from typing import Any

from .config import Settings
from .db import Database
from .internet_client import InternetClient
from .memory import MemoryStore
from .ollama_client import OllamaClient, OllamaError
from .planner import TaskPlanner
from .project_builder import ProjectBuilder
from .project_executor import ProjectExecutor
from .prompts import system_prompt
from .rag import RagIndex
from .router import ModelRouter
from .templates import TemplateManager
from .tools import SafeTools, ToolError, format_tool_result


TOOL_PATTERN = re.compile(r"<tool_call>\s*(\{.*\})\s*</tool_call>", re.DOTALL)
AGENT_MODES = {
    "general": "General assistant mode. Focus on clear answers, practical next steps, and fast summaries.",
    "coder": "Engineering mode. Prefer implementation details, file-aware reasoning, and executable code output.",
    "vision": "Vision mode. Inspect images carefully, mention uncertainty, and extract visible text when possible.",
    "manager": "Project manager mode. Prefer milestones, priorities, risks, and execution sequencing.",
}
PERMISSION_OPTIONS = [
    "none",
    "local-read",
    "local-write",
    "internet-read",
    "internet-download",
    "full",
]


class LocalAgent:
    def __init__(self, settings: Settings, db: Database) -> None:
        self.settings = settings
        self.db = db
        self.ollama = OllamaClient(settings.ollama_base_url)
        self.internet = InternetClient(settings.downloads_dir, max_download_size_mb=settings.max_download_size_mb)
        self.router = ModelRouter(settings)
        self.memory = MemoryStore(db)
        self.rag = RagIndex(
            db,
            settings.knowledge_dir,
            settings.downloads_dir,
            settings.workspace,
            self.ollama,
            settings.embedding_model,
        )
        self.tools = SafeTools(
            settings.workspace,
            internet_client=self.internet,
            internet_enabled=settings.internet_enabled,
            telemetry_hook=self.db.add_telemetry,
            post_download_hook=self._handle_downloaded_content,
        )
        self.templates = TemplateManager(settings.workspace)
        self.project_builder = ProjectBuilder(settings.workspace)
        self.project_executor = ProjectExecutor(settings.workspace)
        self.planner = TaskPlanner()

    def ensure_ready(self) -> dict[str, Any]:
        stats = self.rag.refresh()
        version = self.ollama.version()
        tags = self.ollama.tags()
        return {"version": version, "tags": tags, "rag": stats}

    def chat(
        self,
        conversation_id: str | None,
        user_text: str,
        image_paths: list[Path] | None = None,
        permission_level: str = "none",
        mode: str | None = None,
    ) -> dict[str, Any]:
        conversation_id = conversation_id or str(uuid.uuid4())
        title = user_text[:60] or "New conversation"
        self.db.ensure_conversation(conversation_id, title)
        user_attachments = [{"type": "image", "path": str(path)} for path in image_paths or []]
        user_message_id = self.db.add_message(conversation_id, "user", user_text, attachments=user_attachments)
        self.memory.maybe_learn(user_text, user_message_id)

        route = self.router.decide(user_text, has_images=bool(image_paths))
        active_mode = mode or self.settings.default_mode
        if active_mode == "coder":
            route.model = self.settings.code_model
            route.task_type = "code"
        elif active_mode == "vision":
            route.model = self.settings.vision_model
            route.task_type = "vision"
        rag_hits = self.rag.search(user_text)
        history = self.db.list_messages(conversation_id, limit=12)
        plan_steps = self.planner.build_plan(user_text, route.task_type) if route.requires_plan else []
        workflow_steps = self.planner.build_workflow(user_text, route.task_type, active_mode)
        run_id = str(uuid.uuid4())
        cards: list[dict[str, Any]] = []
        if plan_steps:
            cards.append({"type": "plan", "title": "خطة التنفيذ", "items": plan_steps})
        run_steps = self._prepare_run_steps(workflow_steps)
        self.db.upsert_task_run(
            run_id=run_id,
            conversation_id=conversation_id,
            mode=active_mode,
            title=user_text[:80] or "Workflow",
            status="running",
            progress=0.15,
            summary="تم إنشاء سير عمل أولي للمهمة.",
        )
        self.db.replace_task_steps(run_id, run_steps)
        cards.append({"type": "workflow", "title": "سير التنفيذ", "items": [step["title"] for step in run_steps]})

        prompt = system_prompt(
            memory_lines=self.memory.recall(8),
            rag_context=[f"{hit.path}: {hit.excerpt}" for hit in rag_hits],
            workspace=str(self.settings.workspace),
            mode_prompt=AGENT_MODES.get(active_mode, AGENT_MODES[self.settings.default_mode]),
        )
        messages = [{"role": "system", "content": prompt}]
        messages.extend(self._history_to_chat(history))
        start = time.time()
        answer = ""
        tool_events: list[dict[str, Any]] = []
        generated_artifacts: list[str] = []
        try:
            for _ in range(self.settings.max_tool_steps):
                reply = self.ollama.chat(model=route.model, messages=messages)
                message = reply.get("message", {})
                answer = message.get("content", "")
                tool_call = self._parse_tool_call(answer)
                if not tool_call:
                    break
                if permission_level == "none":
                    answer = (
                        "الوكيل طلب استخدام أداة محلية، لكن وضع الأمان الحالي يمنع التنفيذ التلقائي. "
                        "ارفع مستوى الصلاحية إلى read أو write ثم أعد الإرسال إذا أردت المتابعة."
                    )
                    cards.append({"type": "warning", "title": "مطلوب تأكيد", "content": answer})
                    break
                try:
                    result = self.tools.run(tool_call["tool"], tool_call.get("args", {}), permission_level=permission_level)
                    tool_events.append({"tool": tool_call["tool"], "result": result})
                    artifact_path = result.get("path")
                    if artifact_path:
                        generated_artifacts.append(str(artifact_path))
                    messages.append({"role": "assistant", "content": answer})
                    messages.append({"role": "tool", "content": format_tool_result(result)})
                    cards.append(
                        {
                            "type": "tool",
                            "title": f"Tool: {tool_call['tool']}",
                            "content": format_tool_result(result),
                        }
                    )
                except ToolError as exc:
                    tool_error = {"error": str(exc), "tool": tool_call["tool"]}
                    tool_events.append(tool_error)
                    messages.append({"role": "assistant", "content": answer})
                    messages.append({"role": "tool", "content": format_tool_result(tool_error)})
            else:
                answer = "توقفت سلسلة الأدوات بعد بلوغ الحد الأقصى للخطوات."
        except OllamaError as exc:
            answer = (
                "تعذر الوصول إلى خدمة Ollama المحلية. تأكد أن التطبيق يعمل وأن الخادم يستجيب على "
                f"{self.settings.ollama_base_url}. تفاصيل الخطأ: {exc}"
            )

        latency_ms = int((time.time() - start) * 1000)
        final_run_steps = self._finalize_run_steps(run_steps, generated_artifacts)
        self.db.upsert_task_run(
            run_id=run_id,
            conversation_id=conversation_id,
            mode=active_mode,
            title=user_text[:80] or "Workflow",
            status="completed",
            progress=1.0,
            summary=answer[:300],
        )
        self.db.replace_task_steps(run_id, final_run_steps)
        self.db.add_message(
            conversation_id,
            "assistant",
            answer,
            metadata={
                "model": route.model,
                "task_type": route.task_type,
                "latency_ms": latency_ms,
                "tool_events": tool_events,
                "rag_sources": [hit.path for hit in rag_hits],
                "run_id": run_id,
                "generated_artifacts": generated_artifacts,
            },
        )
        self.db.add_telemetry(
            "chat",
            {
                "conversation_id": conversation_id,
                "model": route.model,
                "task_type": route.task_type,
                "latency_ms": latency_ms,
                "used_tools": len(tool_events),
                "has_images": bool(image_paths),
            },
        )
        if rag_hits:
            cards.append(
                {
                    "type": "sources",
                    "title": "المصادر المسترجعة",
                    "items": [f"{hit.path} (score={hit.score:.2f})" for hit in rag_hits],
                }
            )
        cards.append(
            {
                "type": "meta",
                "title": "تفاصيل التنفيذ",
                "items": [
                    f"model: {route.model}",
                    f"task type: {route.task_type}",
                    f"mode: {active_mode}",
                    f"latency: {latency_ms} ms",
                    f"run: {run_id}",
                ],
            }
        )
        if generated_artifacts:
            cards.append({"type": "artifacts", "title": "الملفات الناتجة", "items": generated_artifacts})
        return {"conversation_id": conversation_id, "answer": answer, "cards": cards}

    def dashboard(self) -> dict[str, Any]:
        saved_settings = self.db.get_all_settings()
        return {
            "documents": self.db.get_documents(),
            "telemetry": self.db.list_telemetry(20),
            "memories": self.db.list_memories(20),
            "modes": [{"id": key, "label": key} for key in AGENT_MODES],
            "runs": self.db.list_task_runs(10),
            "conversations": self.db.list_conversations(20),
            "templates": self.templates.list_templates(),
            "settings": {
                "default_mode": self.settings.default_mode,
                "default_chat_model": self.settings.default_chat_model,
                "code_model": self.settings.code_model,
                "vision_model": self.settings.vision_model,
                "embedding_model": self.settings.embedding_model,
                "internet_enabled": self.settings.internet_enabled,
                "downloads_dir": str(self.settings.downloads_dir),
                "max_download_size_mb": self.settings.max_download_size_mb,
            },
            "saved_settings": saved_settings,
            "permission_options": PERMISSION_OPTIONS,
        }

    def apply_template(self, template_id: str, target_dir: str) -> dict[str, Any]:
        written = self.templates.apply(template_id, target_dir)
        self.db.add_telemetry("template_apply", {"template_id": template_id, "target_dir": target_dir, "written": written})
        return {"template_id": template_id, "target_dir": target_dir, "written": written}

    def build_full_project(
        self,
        description: str,
        target_dir: str,
        project_name: str | None = None,
        allow_external: bool = False,
    ) -> dict[str, Any]:
        conversation_id = str(uuid.uuid4())
        self.db.ensure_conversation(conversation_id, project_name or description[:60] or "Build full project")
        run_id = str(uuid.uuid4())
        steps = [
            {"title": "تحليل الوصف", "details": "تحويل الوصف إلى نوع مشروع مناسب.", "status": "completed"},
            {"title": "اختيار القالب", "details": "تحديد أفضل scaffold أولي.", "status": "completed"},
            {"title": "إنشاء الملفات", "details": "كتابة ملفات المشروع والـ manifest.", "status": "completed"},
            {"title": "إعداد أوامر التشغيل", "details": "إخراج أوامر التثبيت والتشغيل والاختبار.", "status": "completed"},
        ]
        self.db.upsert_task_run(
            run_id=run_id,
            conversation_id=conversation_id,
            mode="builder",
            title=project_name or description[:80] or "Build full project",
            status="running",
            progress=0.2,
            summary="جارٍ بناء المشروع الكامل.",
        )
        self.db.replace_task_steps(run_id, steps)
        result = self.project_builder.build(
            description=description,
            target_dir=target_dir,
            project_name=project_name,
            allow_external=allow_external,
        )
        self.db.upsert_task_run(
            run_id=run_id,
            conversation_id=conversation_id,
            mode="builder",
            title=project_name or description[:80] or "Build full project",
            status="completed",
            progress=1.0,
            summary=f"تم إنشاء مشروع {result['project_name']} داخل {result['target_dir']}.",
        )
        self.db.replace_task_steps(run_id, steps)
        self.db.add_telemetry(
            "project_build",
            {
                "run_id": run_id,
                "conversation_id": conversation_id,
                "target_dir": result["target_dir"],
                "stack": result["stack"],
                "template_id": result["template_id"],
            },
        )
        cards = [
            {"type": "workflow", "title": "مراحل البناء", "items": [step["title"] for step in steps]},
            {"type": "artifacts", "title": "الملفات الناتجة", "items": result["written"]},
            {
                "type": "commands",
                "title": "أوامر المشروع",
                "items": (
                    [f"install: {cmd}" for cmd in result["manifest"]["install_commands"]]
                    + [f"run: {cmd}" for cmd in result["manifest"]["run_commands"]]
                    + [f"test: {cmd}" for cmd in result["manifest"]["test_commands"]]
                ),
            },
        ]
        return {
            "run_id": run_id,
            "conversation_id": conversation_id,
            "project_name": result["project_name"],
            "target_dir": result["target_dir"],
            "stack": result["stack"],
            "manifest": result["manifest"],
            "cards": cards,
        }

    def execute_project(
        self,
        target_dir: str,
        actions: list[str],
        allow_external: bool = False,
    ) -> dict[str, Any]:
        conversation_id = str(uuid.uuid4())
        run_id = str(uuid.uuid4())
        title = f"Execute project: {target_dir}"
        step_titles = {
            "install": "تثبيت الاعتماديات",
            "run": "تشغيل المشروع",
            "test": "اختبار المشروع",
            "smoke": "Smoke test",
        }
        steps = [
            {"title": step_titles.get(action, action), "details": f"Execute {action}", "status": "completed"}
            for action in actions
        ]
        self.db.ensure_conversation(conversation_id, title)
        self.db.upsert_task_run(
            run_id=run_id,
            conversation_id=conversation_id,
            mode="executor",
            title=title,
            status="running",
            progress=0.2,
            summary="جارٍ تنفيذ المشروع.",
        )
        self.db.replace_task_steps(run_id, steps)
        result = self.project_executor.execute(target_dir=target_dir, actions=actions, allow_external=allow_external)
        status = "completed" if result["status"] == "completed" else "failed"
        summary = f"Project execution {status} for {target_dir}."
        self.db.upsert_task_run(
            run_id=run_id,
            conversation_id=conversation_id,
            mode="executor",
            title=title,
            status=status,
            progress=1.0 if status == "completed" else 0.8,
            summary=summary,
        )
        self.db.replace_task_steps(run_id, steps)
        self.db.add_telemetry(
            "project_execute",
            {
                "run_id": run_id,
                "conversation_id": conversation_id,
                "target_dir": target_dir,
                "actions": actions,
                "status": status,
            },
        )
        cards = [
            {"type": "workflow", "title": "Pipeline", "items": [step["title"] for step in steps]},
            {
                "type": "commands",
                "title": "Execution Results",
                "items": [
                    f"{item['command']} -> exit {item['exit_code']} ({item['duration_ms']} ms)"
                    for item in result["results"]
                ],
            },
        ]
        if result["fix_notes"]:
            cards.append({"type": "warning", "title": "Auto Fix Notes", "items": result["fix_notes"]})
        return {
            "run_id": run_id,
            "conversation_id": conversation_id,
            "status": status,
            "results": result["results"],
            "fix_notes": result["fix_notes"],
            "cards": cards,
        }

    def export_conversation(self, conversation_id: str) -> dict[str, Any]:
        conversations = {item["id"]: item for item in self.db.list_conversations(100)}
        conversation = conversations.get(conversation_id)
        if not conversation:
            raise ValueError("Conversation not found.")
        return {
            "conversation": conversation,
            "messages": self.db.get_conversation_messages(conversation_id),
        }

    def import_conversation(self, payload: dict[str, Any]) -> dict[str, Any]:
        conversation = payload.get("conversation") or {}
        title = str(conversation.get("title") or "Imported conversation")
        new_id = str(uuid.uuid4())
        self.db.ensure_conversation(new_id, title)
        imported = 0
        for message in payload.get("messages", []):
            self.db.add_message(
                new_id,
                str(message.get("role", "user")),
                str(message.get("content", "")),
                attachments=message.get("attachments") or [],
                metadata=message.get("metadata") or {},
            )
            imported += 1
        self.db.add_telemetry("conversation_import", {"conversation_id": new_id, "imported_messages": imported})
        return {"conversation_id": new_id, "imported_messages": imported}

    def save_preferences(self, preferences: dict[str, Any]) -> dict[str, Any]:
        for key, value in preferences.items():
            self.db.set_setting(key, value)
        return {"saved": preferences}

    def _handle_downloaded_content(self, result: dict[str, Any]) -> None:
        indexed_sidecar = result.get("indexed_sidecar")
        if indexed_sidecar:
            self.rag.refresh()

    @staticmethod
    def _prepare_run_steps(workflow_steps: list[dict[str, str]]) -> list[dict[str, Any]]:
        prepared = []
        for index, step in enumerate(workflow_steps):
            prepared.append(
                {
                    "title": step["title"],
                    "details": step.get("details", ""),
                    "status": "in_progress" if index == 0 else "pending",
                    "artifact_path": None,
                }
            )
        return prepared

    @staticmethod
    def _finalize_run_steps(workflow_steps: list[dict[str, Any]], artifacts: list[str]) -> list[dict[str, Any]]:
        finalized = []
        for index, step in enumerate(workflow_steps):
            item = dict(step)
            item["status"] = "completed"
            if artifacts and index == 2:
                item["artifact_path"] = artifacts[0]
            finalized.append(item)
        return finalized

    @staticmethod
    def save_upload(upload_dir: Path, name: str, data_base64: str) -> Path:
        ext = Path(name).suffix or ".bin"
        target = upload_dir / f"{uuid.uuid4().hex}{ext}"
        target.write_bytes(base64.b64decode(data_base64))
        return target

    @staticmethod
    def _parse_tool_call(text: str) -> dict[str, Any] | None:
        match = TOOL_PATTERN.search(text or "")
        if not match:
            return None
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            return None

    @staticmethod
    def _history_to_chat(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
        chat_messages = []
        for item in history:
            message: dict[str, Any] = {"role": item["role"], "content": item["content"]}
            images = [attachment["path"] for attachment in item.get("attachments", []) if attachment.get("type") == "image"]
            if images:
                message["images"] = [base64.b64encode(Path(path).read_bytes()).decode("utf-8") for path in images]
            chat_messages.append(message)
        return chat_messages
