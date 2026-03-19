from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .agent import LocalAgent
from .config import load_settings
from .db import Database


SETTINGS = load_settings()
DB = Database(SETTINGS.db_path)
AGENT = LocalAgent(SETTINGS, DB)
STATIC_DIR = SETTINGS.workspace / "static"


class AppHandler(BaseHTTPRequestHandler):
    server_version = "LocalOllamaAgent/0.1"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if not self._authorized():
            return
        if parsed.path == "/api/health":
            self._json(HTTPStatus.OK, {"ok": True, "ready": AGENT.ensure_ready()})
            return
        if parsed.path == "/api/dashboard":
            self._json(HTTPStatus.OK, AGENT.dashboard())
            return
        if parsed.path.startswith("/api/jobs/"):
            job_id = parsed.path.rsplit("/", 1)[-1]
            job = AGENT.get_job(job_id)
            if not job:
                self._json(HTTPStatus.NOT_FOUND, {"error": "Job not found"})
                return
            self._json(HTTPStatus.OK, job)
            return
        self._serve_static(parsed.path)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if not self._authorized():
            return
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length) or b"{}")
        if parsed.path == "/api/chat":
            image_paths = []
            for image in payload.get("images", []):
                image_paths.append(
                    AGENT.save_upload(SETTINGS.uploads_dir, image["name"], image["data_base64"])
                )
            response = AGENT.chat(
                conversation_id=payload.get("conversation_id"),
                user_text=payload.get("message", ""),
                image_paths=image_paths,
                permission_level=str(payload.get("permission_level", "auto")),
                mode=payload.get("mode"),
            )
            self._json(HTTPStatus.OK, response)
            return
        if parsed.path == "/api/templates/apply":
            response = AGENT.apply_template(
                template_id=payload.get("template_id", ""),
                target_dir=payload.get("target_dir", "generated"),
            )
            self._json(HTTPStatus.OK, response)
            return
        if parsed.path == "/api/projects/build":
            if payload.get("async"):
                self._json(HTTPStatus.OK, AGENT.submit_job("build_project", payload))
                return
            response = AGENT.build_full_project(
                description=payload.get("description", ""),
                target_dir=payload.get("target_dir", "generated/project"),
                project_name=payload.get("project_name"),
                allow_external=bool(payload.get("allow_external")),
            )
            self._json(HTTPStatus.OK, response)
            return
        if parsed.path == "/api/projects/execute":
            if payload.get("async"):
                self._json(HTTPStatus.OK, AGENT.submit_job("execute_project", payload))
                return
            response = AGENT.execute_project(
                target_dir=payload.get("target_dir", "generated/project"),
                actions=payload.get("actions", ["install", "run", "smoke"]),
                allow_external=bool(payload.get("allow_external")),
            )
            self._json(HTTPStatus.OK, response)
            return
        if parsed.path == "/api/conversations/export":
            response = AGENT.export_conversation(payload.get("conversation_id", ""))
            self._json(HTTPStatus.OK, response)
            return
        if parsed.path == "/api/conversations/import":
            response = AGENT.import_conversation(payload)
            self._json(HTTPStatus.OK, response)
            return
        if parsed.path == "/api/settings/save":
            response = AGENT.save_preferences(payload.get("preferences", {}))
            self._json(HTTPStatus.OK, response)
            return
        if parsed.path == "/api/reindex":
            self._json(HTTPStatus.OK, AGENT.ensure_ready())
            return
        self._json(HTTPStatus.NOT_FOUND, {"error": "Not found"})

    def _serve_static(self, path: str) -> None:
        rel = "index.html" if path in {"/", ""} else path.lstrip("/")
        file_path = (STATIC_DIR / rel).resolve()
        if STATIC_DIR not in file_path.parents and file_path != STATIC_DIR / "index.html":
            self.send_error(HTTPStatus.FORBIDDEN)
            return
        if not file_path.exists() or not file_path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        content_type = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
        }.get(file_path.suffix, "application/octet-stream")
        data = file_path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _json(self, status: HTTPStatus, payload: dict) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format: str, *args) -> None:
        return

    def _authorized(self) -> bool:
        api_key = AGENT._active_api_key()
        if not api_key:
            return True
        header_value = self.headers.get("X-API-Key", "")
        if header_value == api_key:
            return True
        self._json(HTTPStatus.UNAUTHORIZED, {"error": "Unauthorized"})
        return False


def main() -> None:
    server = ThreadingHTTPServer((SETTINGS.host, SETTINGS.port), AppHandler)
    print(f"Local agent running at http://{SETTINGS.host}:{SETTINGS.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
