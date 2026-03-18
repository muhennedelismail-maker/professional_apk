import tempfile
import unittest
from pathlib import Path

from app.db import Database


class DatabaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "agent.db"
        self.db = Database(self.db_path)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_conversation_round_trip(self) -> None:
        self.db.ensure_conversation("c1", "Title")
        self.db.add_message("c1", "user", "hello")
        self.db.add_message("c1", "assistant", "world")
        conversations = self.db.list_conversations()
        self.assertEqual(conversations[0]["id"], "c1")
        messages = self.db.get_conversation_messages("c1")
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[1]["content"], "world")

    def test_settings_round_trip(self) -> None:
        self.db.set_setting("default_mode", "coder")
        self.assertEqual(self.db.get_setting("default_mode"), "coder")

