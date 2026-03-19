#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "Starting native Ollama service..."
brew services start ollama >/dev/null || true

echo "Starting Open WebUI + SearXNG..."
cd "$ROOT_DIR"
docker compose up -d

echo
echo "Ollama:      http://127.0.0.1:11434"
echo "Open WebUI:  http://127.0.0.1:3000"
echo "SearXNG:     http://127.0.0.1:8080"
