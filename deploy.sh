#!/bin/bash
DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== QuantEdge Production ==="

cd "$DIR"
source .venv/bin/activate

pkill -f "uvicorn api.main" 2>/dev/null || true
pkill -f "next start" 2>/dev/null || true
sleep 1

echo "[backend] Starting on :8000"
nohup uvicorn api.main:app --host 0.0.0.0 --port 8000 --no-access-log > /tmp/quantedge-backend.log 2>&1 &
echo $! > /tmp/quantedge-backend.pid
echo "  PID: $(cat /tmp/quantedge-backend.pid)"

echo "[frontend] Starting on :3000"
cd "$DIR/web"
nohup npx next start -p 3000 > /tmp/quantedge-frontend.log 2>&1 &
echo $! > /tmp/quantedge-frontend.pid
echo "  PID: $(cat /tmp/quantedge-frontend.pid)"

sleep 3

echo ""
echo "  Frontend: http://localhost:3000"
echo "  Backend:  http://localhost:8000/api/health"
echo ""
echo "  Logs: tail -f /tmp/quantedge-*.log"
echo "  Stop:  pkill -f 'uvicorn api.main|next start'"
