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
    provider: str
    rank: int


class InternetClient:
    BLOCKED_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1"}
    BLOCKED_EXTENSIONS = {".exe", ".dmg", ".pkg", ".app", ".sh", ".bat", ".command", ".msi", ".ps1"}

    def __init__(
        self,
        downloads_dir: Path,
        max_download_size_mb: int = 10,
        search_provider: str = "auto",
        search_base_url: str = "",
        ollama_api_key: str = "",
        ollama_web_base_url: str = "https://ollama.com",
        allowed_domains: tuple[str, ...] = (),
    ) -> None:
        self.downloads_dir = downloads_dir.resolve()
        self.max_download_size_bytes = max_download_size_mb * 1024 * 1024
        self.user_agent = "ProfessionalAPKLocalAgent/1.1"
        self.search_provider = (search_provider or "auto").strip().lower()
        self.search_base_url = search_base_url.rstrip("/")
        self.ollama_api_key = ollama_api_key.strip()
        self.ollama_web_base_url = ollama_web_base_url.rstrip("/")
        self.allowed_domains = tuple(domain.lower() for domain in allowed_domains)

    def fetch_url(self, url: str) -> dict[str, Any]:
        parsed = urllib.parse.urlparse(url)
        self._ensure_remote_http_url(parsed)

        provider_used = "direct"
        fallback_used = False
        title = ""
        links: list[str] = []

        if self._should_try_ollama():
            try:
                fetched = self._ollama_web_fetch(url)
                provider_used = "ollama"
                title = str(fetched.get("title", "") or "")
                links = [str(link) for link in fetched.get("links", []) if str(link).startswith(("http://", "https://"))][:20]
                text = str(fetched.get("content", "") or "").strip()
                return {
                    "url": url,
                    "title": title,
                    "status": 200,
                    "content_type": "text/html; charset=utf-8",
                    "text": text[:12000],
                    "links": links,
                    "provider_requested": self.search_provider,
                    "provider_used": provider_used,
                    "fallback_used": fallback_used,
                    "citations": self._citations_from_urls([{"title": title or url, "url": url, "provider": provider_used, "rank": 1}]),
                }
            except InternetError:
                fallback_used = True

        response = self._request(url)
        body = response["body"]
        content_type = response["content_type"]
        extracted = self._extract_text(body, content_type, url)
        if "html" in content_type.lower():
            title = self._extract_title(body.decode("utf-8", errors="ignore"))
            links = self._extract_links(body.decode("utf-8", errors="ignore"), url)
        return {
            "url": url,
            "title": title,
            "status": response["status"],
            "content_type": content_type,
            "text": extracted[:12000],
            "links": links[:20],
            "provider_requested": self.search_provider,
            "provider_used": provider_used,
            "fallback_used": fallback_used,
            "citations": self._citations_from_urls([{"title": title or url, "url": url, "provider": provider_used, "rank": 1}]),
        }

    def fetch_json(self, url: str) -> dict[str, Any]:
        response = self._request(url)
        try:
            parsed = json.loads(response["body"].decode("utf-8", errors="ignore"))
        except json.JSONDecodeError as exc:
            raise InternetError("Response is not valid JSON.") from exc
        return {
            "url": url,
            "status": response["status"],
            "json": parsed,
            "provider_used": "direct",
            "citations": self._citations_from_urls([{"title": url, "url": url, "provider": "direct", "rank": 1}]),
        }

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
            "provider_used": "direct",
            "citations": self._citations_from_urls([{"title": safe_name, "url": url, "provider": "direct", "rank": 1}]),
        }

    def search_web(self, query: str, limit: int = 5) -> dict[str, Any]:
        query = query.strip()
        if not query:
            raise InternetError("Search query is empty.")

        provider_used = ""
        fallback_used = False
        last_error: InternetError | None = None

        for provider in self._provider_sequence():
            try:
                if provider == "ollama":
                    results = self._search_with_ollama(query, limit)
                elif provider == "searxng":
                    results = self._search_with_searxng(query, limit)
                else:
                    results = self._search_with_duckduckgo(query, limit)
                provider_used = provider
                return {
                    "query": query,
                    "provider_requested": self.search_provider,
                    "provider_used": provider_used,
                    "fallback_used": fallback_used,
                    "results": [result.__dict__ for result in results],
                    "citations": self._citations_from_urls([result.__dict__ for result in results]),
                }
            except InternetError as exc:
                last_error = exc
                fallback_used = True
        if last_error:
            raise last_error
        raise InternetError("No search provider is configured.")

    def _provider_sequence(self) -> list[str]:
        requested = self.search_provider or "auto"
        sequence: list[str] = []
        if requested in {"auto", "ollama"} and self._should_try_ollama():
            sequence.append("ollama")
        if requested in {"auto", "ollama", "searxng"} and self.search_base_url:
            sequence.append("searxng")
        if requested in {"auto", "ollama", "duckduckgo", "searxng"}:
            sequence.append("duckduckgo")
        deduped: list[str] = []
        for provider in sequence:
            if provider not in deduped:
                deduped.append(provider)
        return deduped

    def _search_with_ollama(self, query: str, limit: int) -> list[SearchResult]:
        payload = {"query": query, "limit": max(1, min(limit, 10))}
        parsed = self._post_json(f"{self.ollama_web_base_url}/api/web_search", payload, extra_headers=self._ollama_headers())
        items = parsed.get("results") or parsed.get("items") or []
        results = []
        for index, item in enumerate(items[:limit], start=1):
            results.append(
                SearchResult(
                    title=str(item.get("title", "") or ""),
                    url=str(item.get("url", "") or ""),
                    snippet=str(item.get("snippet", "") or item.get("content", "") or ""),
                    provider="ollama",
                    rank=index,
                )
            )
        if not results:
            raise InternetError("Ollama web search returned no results.")
        return results

    def _search_with_searxng(self, query: str, limit: int) -> list[SearchResult]:
        encoded = urllib.parse.quote_plus(query)
        url = f"{self.search_base_url}/search?q={encoded}&format=json"
        response = self._request(url)
        parsed = json.loads(response["body"].decode("utf-8", errors="ignore"))
        results = [
            SearchResult(
                title=str(item.get("title", "") or ""),
                url=str(item.get("url", "") or ""),
                snippet=str(item.get("content", "") or ""),
                provider="searxng",
                rank=index,
            )
            for index, item in enumerate(parsed.get("results", [])[:limit], start=1)
        ]
        if not results:
            raise InternetError("SearXNG returned no results.")
        return results

    def _search_with_duckduckgo(self, query: str, limit: int) -> list[SearchResult]:
        encoded = urllib.parse.quote_plus(query)
        url = f"https://html.duckduckgo.com/html/?q={encoded}"
        response = self._request(url)
        text = response["body"].decode("utf-8", errors="ignore")
        results = self._parse_search_results(text, provider="duckduckgo")[:limit]
        if not results:
            raise InternetError("DuckDuckGo returned no results.")
        return results

    def _ollama_web_fetch(self, url: str) -> dict[str, Any]:
        payload = {"url": url}
        parsed = self._post_json(f"{self.ollama_web_base_url}/api/web_fetch", payload, extra_headers=self._ollama_headers())
        content = str(parsed.get("content", "") or "")
        if not content.strip():
            raise InternetError("Ollama web fetch returned empty content.")
        links = parsed.get("links") or []
        normalized_links = []
        for link in links:
            candidate = ""
            if isinstance(link, str):
                candidate = link
            elif isinstance(link, dict):
                candidate = str(link.get("url", "") or "")
            if candidate.startswith(("http://", "https://")):
                normalized_links.append(candidate)
        return {
            "title": str(parsed.get("title", "") or ""),
            "content": content,
            "links": normalized_links[:20],
        }

    def _request(self, url: str, binary: bool = False) -> dict[str, Any]:
        parsed = urllib.parse.urlparse(url)
        self._ensure_remote_http_url(parsed)
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

    def _post_json(self, url: str, payload: dict[str, Any], extra_headers: dict[str, str] | None = None) -> dict[str, Any]:
        data = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json", "User-Agent": self.user_agent}
        if extra_headers:
            headers.update(extra_headers)
        request = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                body = response.read(self.max_download_size_bytes + 1)
                if len(body) > self.max_download_size_bytes:
                    raise InternetError("Remote API response exceeded the configured size limit.")
                return json.loads(body.decode("utf-8", errors="ignore"))
        except urllib.error.URLError as exc:
            raise InternetError(f"Network request failed: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise InternetError("Remote API response was not valid JSON.") from exc

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

    def _parse_search_results(self, html_text: str, provider: str) -> list[SearchResult]:
        results: list[SearchResult] = []
        pattern = re.compile(
            r'<a[^>]*class="[^"]*result__a[^"]*"[^>]*href="(?P<url>[^"]+)"[^>]*>(?P<title>.*?)</a>',
            re.IGNORECASE | re.DOTALL,
        )
        snippet_pattern = re.compile(r'<a[^>]*class="[^"]*result__snippet[^"]*"[^>]*>(?P<snippet>.*?)</a>', re.IGNORECASE | re.DOTALL)
        snippets = [self._clean_html(match.group("snippet")) for match in snippet_pattern.finditer(html_text)]
        for index, match in enumerate(pattern.finditer(html_text), start=1):
            results.append(
                SearchResult(
                    title=self._clean_html(match.group("title")),
                    url=html.unescape(match.group("url")),
                    snippet=snippets[index - 1] if index - 1 < len(snippets) else "",
                    provider=provider,
                    rank=index,
                )
            )
        return results

    @staticmethod
    def _clean_html(text: str) -> str:
        text = re.sub(r"<[^>]+>", " ", text)
        text = html.unescape(text)
        return re.sub(r"\s+", " ", text).strip()

    @staticmethod
    def _extract_title(html_text: str) -> str:
        match = re.search(r"<title[^>]*>(.*?)</title>", html_text, flags=re.IGNORECASE | re.DOTALL)
        if not match:
            return ""
        return InternetClient._clean_html(match.group(1))

    @staticmethod
    def _extract_links(html_text: str, source_url: str) -> list[str]:
        links = []
        base = urllib.parse.urlparse(source_url)
        for match in re.finditer(r'href="([^"]+)"', html_text, flags=re.IGNORECASE):
            href = html.unescape(match.group(1)).strip()
            if not href or href.startswith(("#", "javascript:", "mailto:")):
                continue
            links.append(urllib.parse.urljoin(f"{base.scheme}://{base.netloc}", href))
        deduped = []
        for link in links:
            if link not in deduped:
                deduped.append(link)
        return deduped

    @staticmethod
    def _filename_from_url(url: str) -> str:
        path = urllib.parse.urlparse(url).path
        name = Path(path).name or "download.bin"
        suffix = Path(name).suffix.lower()
        if suffix in InternetClient.BLOCKED_EXTENSIONS:
            raise InternetError("Refusing to download executable or installer file types.")
        return re.sub(r"[^A-Za-z0-9._-]", "-", name)

    def _citations_from_urls(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        citations = []
        for index, item in enumerate(items, start=1):
            url = str(item.get("url", "") or "")
            if not url:
                continue
            citations.append(
                {
                    "id": index,
                    "title": str(item.get("title", "") or url),
                    "url": url,
                    "provider": str(item.get("provider", "") or "direct"),
                    "rank": int(item.get("rank", index) or index),
                }
            )
        return citations

    def _ollama_headers(self) -> dict[str, str]:
        if not self.ollama_api_key:
            raise InternetError("OLLAMA_API_KEY is not configured.")
        return {"Authorization": f"Bearer {self.ollama_api_key}"}

    def _should_try_ollama(self) -> bool:
        return bool(self.ollama_api_key)

    def _ensure_remote_http_url(self, parsed: urllib.parse.ParseResult) -> None:
        if parsed.scheme not in {"http", "https"}:
            raise InternetError("Only http and https URLs are allowed.")
        self._guard_remote_target(parsed)

    def _guard_remote_target(self, parsed: urllib.parse.ParseResult) -> None:
        host = (parsed.hostname or "").lower()
        if host in self.BLOCKED_HOSTS:
            raise InternetError("Access to localhost or loopback targets is blocked for internet tools.")
        if self.allowed_domains and not any(host == domain or host.endswith("." + domain) for domain in self.allowed_domains):
            raise InternetError("This domain is not allowed by the current domain allowlist.")
        try:
            ip = ipaddress.ip_address(host)
        except ValueError:
            return
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            raise InternetError("Access to private or reserved network ranges is blocked for internet tools.")
