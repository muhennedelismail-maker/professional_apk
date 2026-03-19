import tempfile
import unittest
from pathlib import Path

from app.internet_client import InternetClient
from app.tools import SafeTools, ToolError


class FakeInternetClient(InternetClient):
    def __init__(self, downloads: Path) -> None:
        super().__init__(downloads)

    def fetch_url(self, url: str) -> dict:
        return {"url": url, "text": "ok", "citations": [{"url": url, "title": url, "provider": "fake"}]}

    def download_file(self, url: str, filename: str | None = None) -> dict:
        return {"url": url, "path": str(self.downloads_dir / (filename or "file.txt")), "citations": [{"url": url, "title": url, "provider": "fake"}]}


class ToolPermissionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp_dir.name)
        downloads = self.workspace / "downloads"
        downloads.mkdir()
        self.tools = SafeTools(
            self.workspace,
            internet_client=InternetClient(downloads),
            internet_enabled=True,
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_write_requires_write_permission(self) -> None:
        with self.assertRaises(ToolError):
            self.tools.run("write_file", {"path": "a.txt", "content": "x"}, permission_level="local-read")

    def test_read_allowed_with_read_permission(self) -> None:
        path = self.workspace / "a.txt"
        path.write_text("hello", encoding="utf-8")
        result = self.tools.run("read_file", {"path": "a.txt"}, permission_level="local-read")
        self.assertEqual(result["content"], "hello")

    def test_web_fetch_requires_internet_permission(self) -> None:
        with self.assertRaises(ToolError):
            self.tools.run("web_fetch", {"url": "https://example.com"}, permission_level="local-read")

    def test_auto_allows_web_fetch(self) -> None:
        tools = SafeTools(self.workspace, internet_client=FakeInternetClient(self.workspace / "downloads"), internet_enabled=True)
        result = tools.run("web_fetch", {"url": "https://example.com"}, permission_level="auto")
        self.assertEqual(result["url"], "https://example.com")

    def test_auto_allows_download_file(self) -> None:
        tools = SafeTools(self.workspace, internet_client=FakeInternetClient(self.workspace / "downloads"), internet_enabled=True)
        result = tools.run("download_file", {"url": "https://example.com/file.txt"}, permission_level="auto")
        self.assertIn("path", result)
