from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
import re
from pathlib import Path

from .db import Database
from .ollama_client import OllamaClient, OllamaError


def tokenize(text: str) -> list[str]:
    return re.findall(r"[\w\u0600-\u06FF]+", text.lower())


def chunk_text(text: str, max_words: int = 160) -> list[str]:
    words = text.split()
    if not words:
        return []
    return [" ".join(words[i : i + max_words]) for i in range(0, len(words), max_words)]


@dataclass
class RetrievalHit:
    path: str
    score: float
    excerpt: str


class RagIndex:
    def __init__(
        self,
        db: Database,
        knowledge_dir: Path,
        downloads_dir: Path,
        workspace: Path,
        ollama: OllamaClient,
        embedding_model: str,
    ) -> None:
        self.db = db
        self.knowledge_dir = knowledge_dir
        self.downloads_dir = downloads_dir
        self.workspace = workspace
        self.ollama = ollama
        self.embedding_model = embedding_model

    def refresh(self) -> dict[str, int]:
        indexed_docs = 0
        indexed_chunks = 0
        embedded_chunks = 0
        for root in (self.knowledge_dir, self.downloads_dir):
            for path in root.rglob("*"):
                if not path.is_file():
                    continue
                if path.suffix.lower() not in {".txt", ".md", ".py", ".js", ".ts", ".json", ".html", ".css", ".xml", ".csv"}:
                    continue
                text = self._read_text(path)
                if not text.strip():
                    continue
                chunks = chunk_text(text)
                sha256 = hashlib.sha256(text.encode("utf-8")).hexdigest()
                rel_path = str(path.relative_to(self.workspace))
                self.db.replace_document(rel_path, sha256, len(text.encode("utf-8")), chunks)
                indexed_docs += 1
                indexed_chunks += len(chunks)
        for chunk in self.db.get_chunks():
            try:
                vector = self.ollama.embed(self.embedding_model, str(chunk["content"]))
            except OllamaError:
                break
            self.db.save_embedding(int(chunk["id"]), vector, self.embedding_model)
            embedded_chunks += 1
        return {"documents": indexed_docs, "chunks": indexed_chunks, "embedded_chunks": embedded_chunks}

    def search(self, query: str, limit: int = 4) -> list[RetrievalHit]:
        query_tokens = tokenize(query)
        if not query_tokens:
            return []
        all_chunks = self.db.get_chunks_with_embeddings()
        df: dict[str, int] = {}
        chunk_tokens: list[tuple[dict[str, object], list[str]]] = []
        for chunk in all_chunks:
            tokens = tokenize(chunk["content"])
            chunk_tokens.append((chunk, tokens))
            for token in set(tokens):
                df[token] = df.get(token, 0) + 1
        total_docs = max(len(chunk_tokens), 1)
        hits: list[RetrievalHit] = []
        try:
            query_vector = self.ollama.embed(self.embedding_model, query)
        except OllamaError:
            query_vector = None
        for chunk, tokens in chunk_tokens:
            if not tokens:
                continue
            score = 0.0
            for token in query_tokens:
                tf = tokens.count(token) / len(tokens)
                idf = math.log((1 + total_docs) / (1 + df.get(token, 0))) + 1
                score += tf * idf
            vector = chunk.get("vector")
            if query_vector and vector:
                score += self._cosine_similarity(query_vector, vector) * 2.5
            if score <= 0:
                continue
            hits.append(
                RetrievalHit(
                    path=str(chunk["document_path"]),
                    score=score,
                    excerpt=str(chunk["content"])[:500],
                )
            )
        hits.sort(key=lambda item: item.score, reverse=True)
        return hits[:limit]

    @staticmethod
    def _read_text(path: Path) -> str:
        try:
            return path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return path.read_text(encoding="utf-8", errors="ignore")

    @staticmethod
    def _cosine_similarity(left: list[float], right: list[float]) -> float:
        if not left or not right or len(left) != len(right):
            return 0.0
        numerator = sum(a * b for a, b in zip(left, right))
        left_norm = math.sqrt(sum(a * a for a in left))
        right_norm = math.sqrt(sum(b * b for b in right))
        if left_norm == 0 or right_norm == 0:
            return 0.0
        return numerator / (left_norm * right_norm)
