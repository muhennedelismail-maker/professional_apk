from __future__ import annotations

import html
import ipaddress
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class InternetError(RuntimeError):
    pass


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str


class InternetClient:
    BLOCKED_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1"}
    BLOCKED_EXTENSIONS = {".exe", ".dmg", ".pkg", ".app", ".sh", ".bat", ".command", ".msi", ".ps1"}

    def __init__(self, downloads_dir: Path, max_download_size_mb: int = 10) -> None:
        self.downloads_dir = downloads_dir.resolve()
        self.max_download_size_bytes = max_download_size_mb * 1024 * 1024
        self.user_agent = "ProfessionalAPKLocalAgent/1.0"

    def fetch_url(self, url: str) -> dict[str, Any]:
        response = self._request(url)
        body = response["body"]
        content_type = response["content_type"]
        extracted = self._extract_text(body, content_type, url)
        return {
            "url": url,
            "status": response["status"],
            "content_type": content_type,
            "text": extracted[:12000],
        }

    def fetch_json(self, url: str) -> dict[str, Any]:
        response = self._request(url)
        try:
            parsed = json.loads(response["body"].decode("utf-8", errors="ignore"))
        except json.JSONDecodeError as exc:
            raise InternetError("Response is not valid JSON.") from exc
        return {"url": url, "status": response["status"], "json": parsed}

    def download_file(self, url: str, filename: str | None = None) -> dict[str, Any]:
        response = self._request(url, binary=True)
        safe_name = filename or self._filename_from_url(url)
        target = self.downloads_dir / safe_name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(response["body"])
        extracted_text = self._extract_text(response["body"], response["content_type"], url)
        if extracted_text:
            sidecar = target.with_suffix(target.suffix + ".txt")
            sidecar.write_text(extracted_text, encoding="utf-8")
        return {
            "url": url,
            "path": str(target),
            "content_type": response["content_type"],
            "size_bytes": len(response["body"]),
            "indexed_sidecar": str(target.with_suffix(target.suffix + ".txt")) if extracted_text else None,
        }

    def search_web(self, query: str, limit: int = 5) -> dict[str, Any]:
        encoded = urllib.parse.quote_plus(query)
        url = f"https://html.duckduckgo.com/html/?q={encoded}"
        response = self._request(url)
        text = response["body"].decode("utf-8", errors="ignore")
        results = self._parse_search_results(text)[:limit]
        return {
            "query": query,
            "results": [result.__dict__ for result in results],
        }

    def _request(self, url: str, binary: bool = False) -> dict[str, Any]:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            raise InternetError("Only http and https URLs are allowed.")
        self._guard_remote_target(parsed)
        req = urllib.request.Request(url, headers={"User-Agent": self.user_agent})
        try:
            with urllib.request.urlopen(req, timeout=20) as response:
                body = response.read(self.max_download_size_bytes + 1)
                if len(body) > self.max_download_size_bytes:
                    raise InternetError("Downloaded payload exceeds the configured size limit.")
                return {
                    "status": response.getcode(),
                    "body": body,
                    "content_type": response.headers.get("Content-Type", "application/octet-stream"),
                }
        except urllib.error.URLError as exc:
            raise InternetError(f"Network request failed: {exc}") from exc

    def _extract_text(self, body: bytes, content_type: str, url: str) -> str:
        lowered_type = content_type.lower()
        if "json" in lowered_type or url.lower().endswith(".json"):
            try:
                parsed = json.loads(body.decode("utf-8", errors="ignore"))
                return json.dumps(parsed, ensure_ascii=False, indent=2)
            except json.JSONDecodeError:
                return body.decode("utf-8", errors="ignore")
        if "html" in lowered_type or url.lower().endswith((".html", ".htm")):
            raw = body.decode("utf-8", errors="ignore")
            raw = re.sub(r"<script[\s\S]*?</script>", " ", raw, flags=re.IGNORECASE)
            raw = re.sub(r"<style[\s\S]*?</style>", " ", raw, flags=re.IGNORECASE)
            raw = re.sub(r"<[^>]+>", " ", raw)
            raw = html.unescape(raw)
            return re.sub(r"\s+", " ", raw).strip()
        if any(token in lowered_type for token in ("text/", "xml", "csv")) or url.lower().endswith((".txt", ".md", ".csv", ".xml")):
            return body.decode("utf-8", errors="ignore")
        return ""

    def _parse_search_results(self, html_text: str) -> list[SearchResult]:
        results: list[SearchResult] = []
        pattern = re.compile(
            r'<a[^>]*class="[^"]*result__a[^"]*"[^>]*href="(?P<url>[^"]+)"[^>]*>(?P<title>.*?)</a>',
            re.IGNORECASE | re.DOTALL,
        )
        snippet_pattern = re.compile(r'<a[^>]*class="[^"]*result__snippet[^"]*"[^>]*>(?P<snippet>.*?)</a>', re.IGNORECASE | re.DOTALL)
        snippets = [self._clean_html(match.group("snippet")) for match in snippet_pattern.finditer(html_text)]
        for index, match in enumerate(pattern.finditer(html_text)):
            results.append(
                SearchResult(
                    title=self._clean_html(match.group("title")),
                    url=html.unescape(match.group("url")),
                    snippet=snippets[index] if index < len(snippets) else "",
                )
            )
        return results

    @staticmethod
    def _clean_html(text: str) -> str:
        text = re.sub(r"<[^>]+>", " ", text)
        text = html.unescape(text)
        return re.sub(r"\s+", " ", text).strip()

    @staticmethod
    def _filename_from_url(url: str) -> str:
        path = urllib.parse.urlparse(url).path
        name = Path(path).name or "download.bin"
        suffix = Path(name).suffix.lower()
        if suffix in InternetClient.BLOCKED_EXTENSIONS:
            raise InternetError("Refusing to download executable or installer file types.")
        return re.sub(r"[^A-Za-z0-9._-]", "-", name)

    def _guard_remote_target(self, parsed: urllib.parse.ParseResult) -> None:
        host = (parsed.hostname or "").lower()
        if host in self.BLOCKED_HOSTS:
            raise InternetError("Access to localhost or loopback targets is blocked for internet tools.")
        try:
            ip = ipaddress.ip_address(host)
        except ValueError:
            return
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            raise InternetError("Access to private or reserved network ranges is blocked for internet tools.")
