from __future__ import annotations

import re

from .db import Database


class MemoryStore:
    def __init__(self, db: Database) -> None:
        self.db = db

    def recall(self, limit: int = 10) -> list[str]:
        memories = self.db.list_memories(limit=limit)
        return [item["content"] for item in memories]

    def maybe_learn(self, user_message: str, source_message_id: int) -> None:
        text = user_message.strip()
        patterns = [
            r"اريد (.+)",
            r"أفضل (.+)",
            r"مشروعي (.+)",
            r"اسمي (.+)",
            r"my name is (.+)",
            r"i prefer (.+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                learned = match.group(0).strip()
                self.db.save_memory("preference", learned, source_message_id)
                break
