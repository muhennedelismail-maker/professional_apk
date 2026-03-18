from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProjectTemplate:
    id: str
    name: str
    description: str
    files: dict[str, str]


TEMPLATES = {
    "python-api": ProjectTemplate(
        id="python-api",
        name="Python API",
        description="Simple Python HTTP JSON API scaffold.",
        files={
            "main.py": """from http.server import BaseHTTPRequestHandler, HTTPServer\nimport json\n\n\nclass App(BaseHTTPRequestHandler):\n    def do_GET(self):\n        if self.path == '/health':\n            self.send_response(200)\n            self.send_header('Content-Type', 'application/json')\n            self.end_headers()\n            self.wfile.write(json.dumps({'ok': True}).encode())\n            return\n        self.send_response(404)\n        self.end_headers()\n\n\nif __name__ == '__main__':\n    server = HTTPServer(('127.0.0.1', 8000), App)\n    print('Listening on http://127.0.0.1:8000')\n    server.serve_forever()\n""",
            "README.md": "# Python API Template\n\nRun with:\n\n```bash\npython3 main.py\n```\n",
        },
    ),
    "web-starter": ProjectTemplate(
        id="web-starter",
        name="Web Starter",
        description="Basic static web app with HTML/CSS/JS.",
        files={
            "index.html": "<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'><title>Starter</title><link rel='stylesheet' href='styles.css'></head><body><h1>Starter App</h1><script src='app.js'></script></body></html>\n",
            "styles.css": "body { font-family: Georgia, serif; margin: 40px; background: #f7f1e8; color: #1d1b17; }\n",
            "app.js": "console.log('starter ready');\n",
        },
    ),
    "flask-api": ProjectTemplate(
        id="flask-api",
        name="Flask API",
        description="Minimal Flask API structure.",
        files={
            "app.py": "from flask import Flask, jsonify\n\napp = Flask(__name__)\n\n@app.get('/health')\ndef health():\n    return jsonify({'ok': True})\n\nif __name__ == '__main__':\n    app.run(debug=True)\n",
            "requirements.txt": "flask>=3.0.0\n",
            "README.md": "# Flask API\n\n```bash\npip install -r requirements.txt\npython3 app.py\n```\n",
        },
    ),
    "fastapi-api": ProjectTemplate(
        id="fastapi-api",
        name="FastAPI API",
        description="Minimal FastAPI scaffold.",
        files={
            "main.py": "from fastapi import FastAPI\n\napp = FastAPI()\n\n@app.get('/health')\ndef health():\n    return {'ok': True}\n",
            "requirements.txt": "fastapi>=0.115.0\nuvicorn>=0.30.0\n",
            "README.md": "# FastAPI API\n\n```bash\npip install -r requirements.txt\nuvicorn main:app --reload\n```\n",
        },
    ),
    "node-api": ProjectTemplate(
        id="node-api",
        name="Node API",
        description="Simple Node HTTP API.",
        files={
            "server.js": "const http = require('http');\n\nconst server = http.createServer((req, res) => {\n  if (req.url === '/health') {\n    res.writeHead(200, { 'Content-Type': 'application/json' });\n    return res.end(JSON.stringify({ ok: true }));\n  }\n  res.writeHead(404);\n  res.end();\n});\n\nserver.listen(3000, '127.0.0.1', () => {\n  console.log('Listening on http://127.0.0.1:3000');\n});\n",
            "package.json": "{\n  \"name\": \"node-api-template\",\n  \"version\": \"1.0.0\",\n  \"private\": true,\n  \"scripts\": {\n    \"start\": \"node server.js\"\n  }\n}\n",
        },
    ),
    "react-starter": ProjectTemplate(
        id="react-starter",
        name="React Starter",
        description="Lightweight React starter without build tooling assumptions.",
        files={
            "index.html": "<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'><title>React Starter</title><script crossorigin src='https://unpkg.com/react@18/umd/react.development.js'></script><script crossorigin src='https://unpkg.com/react-dom@18/umd/react-dom.development.js'></script><script defer src='app.js'></script></head><body><div id='root'></div></body></html>\n",
            "app.js": "const root = ReactDOM.createRoot(document.getElementById('root'));\nroot.render(React.createElement('main', null, React.createElement('h1', null, 'React Starter')));\n",
        },
    ),
}


class TemplateManager:
    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace.resolve()

    def list_templates(self) -> list[dict[str, str]]:
        return [
            {"id": template.id, "name": template.name, "description": template.description}
            for template in TEMPLATES.values()
        ]

    def apply(self, template_id: str, target_dir: str) -> list[str]:
        template = TEMPLATES.get(template_id)
        if not template:
            raise ValueError(f"Unknown template: {template_id}")
        target = (self.workspace / target_dir).resolve()
        try:
            target.relative_to(self.workspace)
        except ValueError as exc:
            raise ValueError("Target directory escapes workspace.")
        target.mkdir(parents=True, exist_ok=True)
        written = []
        for rel_path, content in template.files.items():
            path = target / rel_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            written.append(str(path.relative_to(self.workspace)))
        return written
