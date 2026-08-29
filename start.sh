#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

command -v python >/dev/null 2>&1 || { echo "Python 3.11+ is required"; exit 1; }
command -v npm >/dev/null 2>&1 || { echo "Node.js 20+ is required"; exit 1; }

if [[ ! -d frontend/node_modules ]]; then
  npm --prefix frontend install
fi

python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000 &
BACKEND_PID=$!
npm --prefix frontend run dev -- --host 127.0.0.1 --port 5173 &
FRONTEND_PID=$!

cleanup() {
  kill "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "Frontend: http://127.0.0.1:5173"
echo "Backend:  http://127.0.0.1:8000"
wait
