from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os


@dataclass(frozen=True)
class Settings:
    workspace: Path
    data_dir: Path
    uploads_dir: Path
    knowledge_dir: Path
    db_path: Path
    host: str
    port: int
    ollama_base_url: str
    default_chat_model: str
    code_model: str
    vision_model: str
    embedding_model: str
    max_tool_steps: int
    default_mode: str


def load_settings() -> Settings:
    workspace = Path(os.getenv("AGENT_WORKSPACE", Path.cwd())).resolve()
    data_dir = workspace / ".agent"
    uploads_dir = data_dir / "uploads"
    knowledge_dir = workspace / "knowledge"
    for path in (data_dir, uploads_dir, knowledge_dir):
        path.mkdir(parents=True, exist_ok=True)

    return Settings(
        workspace=workspace,
        data_dir=data_dir,
        uploads_dir=uploads_dir,
        knowledge_dir=knowledge_dir,
        db_path=data_dir / "agent.db",
        host=os.getenv("AGENT_HOST", "127.0.0.1"),
        port=int(os.getenv("AGENT_PORT", "8765")),
        ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
        default_chat_model=os.getenv("DEFAULT_CHAT_MODEL", "qwen2.5-coder:7b"),
        code_model=os.getenv("CODE_MODEL", "qwen2.5-coder:7b"),
        vision_model=os.getenv("VISION_MODEL", "qwen2.5vl:latest"),
        embedding_model=os.getenv("EMBEDDING_MODEL", "nomic-embed-text"),
        max_tool_steps=int(os.getenv("MAX_TOOL_STEPS", "4")),
        default_mode=os.getenv("DEFAULT_AGENT_MODE", "general"),
    )
