#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "Stopping Open WebUI + SearXNG..."
cd "$ROOT_DIR"
docker compose down

echo "Stopping native Ollama service..."
brew services stop ollama >/dev/null || true
