import json
import tempfile
import unittest
from pathlib import Path

from app.project_executor import ProjectExecutor


class ProjectExecutorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp_dir.name)
        self.executor = ProjectExecutor(self.workspace)
        self.project_dir = self.workspace / "generated/demo"
        self.project_dir.mkdir(parents=True)
        manifest = {
            "install_commands": [],
            "run_commands": ['python3 -c "print(\'ok\')"'],
            "test_commands": ['python3 -c "print(\'smoke\')"'],
        }
        (self.project_dir / "project_spec.json").write_text(json.dumps(manifest), encoding="utf-8")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_execute_run_and_smoke(self) -> None:
        result = self.executor.execute("generated/demo", ["run", "smoke"])
        self.assertEqual(result["status"], "completed")
        self.assertEqual(len(result["results"]), 2)
