import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.internet_client import InternetClient


class _FakeResponse:
    def __init__(self, body: bytes, content_type: str = "text/plain", status: int = 200) -> None:
        self._body = io.BytesIO(body)
        self._content_type = content_type
        self._status = status
        self.headers = {"Content-Type": content_type}

    def read(self, size: int = -1) -> bytes:
        return self._body.read(size)

    def getcode(self) -> int:
        return self._status

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class InternetClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.downloads = Path(self.temp_dir.name) / "downloads"
        self.downloads.mkdir()
        self.client = InternetClient(self.downloads, max_download_size_mb=1, allowed_domains=("example.com",))

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    @patch("urllib.request.urlopen")
    def test_fetch_json(self, mock_urlopen) -> None:
        mock_urlopen.return_value = _FakeResponse(json.dumps({"ok": True}).encode(), content_type="application/json")
        result = self.client.fetch_json("https://example.com/data.json")
        self.assertTrue(result["json"]["ok"])

    @patch("urllib.request.urlopen")
    def test_fetch_url_extracts_html(self, mock_urlopen) -> None:
        mock_urlopen.return_value = _FakeResponse(b"<html><body><h1>Hello</h1><p>World</p></body></html>", content_type="text/html")
        result = self.client.fetch_url("https://example.com/page")
        self.assertIn("Hello", result["text"])

    @patch("urllib.request.urlopen")
    def test_download_file(self, mock_urlopen) -> None:
        mock_urlopen.return_value = _FakeResponse(b"downloaded text", content_type="text/plain")
        result = self.client.download_file("https://example.com/file.txt")
        self.assertTrue(Path(result["path"]).exists())
        self.assertTrue(Path(result["indexed_sidecar"]).exists())

    def test_block_localhost_targets(self) -> None:
        with self.assertRaises(Exception):
            self.client.fetch_url("http://127.0.0.1/private")

    def test_block_non_allowlisted_domain(self) -> None:
        with self.assertRaises(Exception):
            self.client.fetch_url("https://not-allowed.test/page")
