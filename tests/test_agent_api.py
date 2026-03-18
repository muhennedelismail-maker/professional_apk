import tempfile
import unittest
from pathlib import Path

from app.agent import LocalAgent
from app.config import Settings
from app.db import Database


class FakeOllama:
    def version(self):
        return {"version": "test"}

    def tags(self):
        return {"models": []}

    def embed(self, model, text):
        return [0.0, 0.0, 0.0]

    def chat(self, model, messages):
        return {"message": {"content": "رد اختباري"}}


class AgentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp_dir.name)
        (self.workspace / "knowledge").mkdir()
        (self.workspace / "static").mkdir()
        settings = Settings(
            workspace=self.workspace,
            data_dir=self.workspace / ".agent",
            uploads_dir=self.workspace / ".agent" / "uploads",
            knowledge_dir=self.workspace / "knowledge",
            db_path=self.workspace / ".agent" / "agent.db",
            host="127.0.0.1",
            port=8765,
            ollama_base_url="http://127.0.0.1:11434",
            default_chat_model="chat",
            code_model="code",
            vision_model="vision",
            embedding_model="embed",
            max_tool_steps=2,
            default_mode="general",
        )
        settings.data_dir.mkdir()
        settings.uploads_dir.mkdir()
        self.db = Database(settings.db_path)
        self.agent = LocalAgent(settings, self.db)
        self.agent.ollama = FakeOllama()
        self.agent.rag.ollama = self.agent.ollama

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_dashboard_contains_templates(self) -> None:
        dashboard = self.agent.dashboard()
        self.assertTrue(dashboard["templates"])

    def test_chat_creates_run(self) -> None:
        result = self.agent.chat(None, "مرحبا", permission_level="none", mode="general")
        self.assertIn("conversation_id", result)
        runs = self.db.list_task_runs()
        self.assertEqual(len(runs), 1)
