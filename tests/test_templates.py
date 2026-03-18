import tempfile
import unittest
from pathlib import Path

from app.templates import TemplateManager


class TemplateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp_dir.name)
        self.manager = TemplateManager(self.workspace)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_apply_python_api_template(self) -> None:
        written = self.manager.apply("python-api", "generated/python-api")
        self.assertIn("generated/python-api/main.py", written)
        self.assertTrue((self.workspace / "generated/python-api/main.py").exists())

