import tempfile
import unittest
from pathlib import Path

from app.project_builder import ProjectBuilder


class ProjectBuilderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp_dir.name)
        self.builder = ProjectBuilder(self.workspace)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_build_fastapi_project(self) -> None:
        result = self.builder.build(
            description="Create a FastAPI service for health checks",
            target_dir="generated/fastapi-app",
            project_name="fastapi-app",
        )
        self.assertEqual(result["stack"], "fastapi")
        self.assertTrue((self.workspace / "generated/fastapi-app/project_spec.json").exists())
        self.assertTrue((self.workspace / "generated/fastapi-app/NEXT_STEPS.md").exists())
