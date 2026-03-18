import tempfile
import unittest
from pathlib import Path

from app.tools import SafeTools, ToolError


class ToolPermissionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp_dir.name)
        self.tools = SafeTools(self.workspace)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_write_requires_write_permission(self) -> None:
        with self.assertRaises(ToolError):
            self.tools.run("write_file", {"path": "a.txt", "content": "x"}, permission_level="read")

    def test_read_allowed_with_read_permission(self) -> None:
        path = self.workspace / "a.txt"
        path.write_text("hello", encoding="utf-8")
        result = self.tools.run("read_file", {"path": "a.txt"}, permission_level="read")
        self.assertEqual(result["content"], "hello")

