from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any


class OllamaError(RuntimeError):
    pass


class OllamaClient:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}{path}",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=180) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise OllamaError(f"Failed to reach Ollama at {self.base_url}: {exc}") from exc

    def _get(self, path: str) -> dict[str, Any]:
        req = urllib.request.Request(f"{self.base_url}{path}", method="GET")
        try:
            with urllib.request.urlopen(req, timeout=20) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise OllamaError(f"Failed to reach Ollama at {self.base_url}: {exc}") from exc

    def version(self) -> dict[str, Any]:
        return self._get("/api/version")

    def tags(self) -> dict[str, Any]:
        return self._get("/api/tags")

    def chat(self, model: str, messages: list[dict[str, Any]], options: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._post(
            "/api/chat",
            {"model": model, "messages": messages, "stream": False, "options": options or {}},
        )

    def embed(self, model: str, text: str) -> list[float]:
        response = self._post("/api/embed", {"model": model, "input": text})
        embeddings = response.get("embeddings") or []
        if not embeddings:
            raise OllamaError("Embedding response did not include vectors.")
        return embeddings[0]
