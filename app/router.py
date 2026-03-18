from __future__ import annotations

from dataclasses import dataclass
import re

from .config import Settings


CODE_HINTS = (
    "code",
    "bug",
    "debug",
    "refactor",
    "python",
    "javascript",
    "typescript",
    "node",
    "api",
    "sql",
    "regex",
    "build",
    "fix",
    "برنامج",
    "تطبيق",
    "كود",
    "برمجة",
    "بايثون",
    "جافاسكربت",
    "اصنع",
    "ابن",
)

LONG_TASK_HINTS = (
    "build",
    "create",
    "design",
    "plan",
    "project",
    "app",
    "workflow",
    "automation",
    "system",
    "ابن",
    "اصنع",
    "نفذ",
    "مشروع",
    "خطة",
    "نظام",
    "تطبيق",
)


@dataclass
class RouteDecision:
    model: str
    task_type: str
    requires_plan: bool


class ModelRouter:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def decide(self, user_text: str, has_images: bool) -> RouteDecision:
        lowered = user_text.lower()
        requires_plan = any(hint in lowered for hint in LONG_TASK_HINTS) or len(user_text.split()) > 60
        if has_images:
            return RouteDecision(model=self.settings.vision_model, task_type="vision", requires_plan=requires_plan)
        if any(hint in lowered for hint in CODE_HINTS) or re.search(r"[{}();<>]|```", user_text):
            return RouteDecision(model=self.settings.code_model, task_type="code", requires_plan=requires_plan)
        return RouteDecision(model=self.settings.default_chat_model, task_type="chat", requires_plan=requires_plan)
