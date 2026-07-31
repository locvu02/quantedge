#!/bin/bash
DIR="$(cd "$(dirname "$0")" && pwd)"

pkill -f "uvicorn api.main" 2>/dev/null || true
pkill -f "next dev" 2>/dev/null || true
sleep 1

echo "=== QuantEdge Trading Platform ==="
echo ""

cd "$DIR"
source .venv/bin/activate
uvicorn api.main:app --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!
echo "Backend PID: $BACKEND_PID"

cd "$DIR/web"
npx next dev -p 3000 &
FRONTEND_PID=$!
echo "Frontend PID: $FRONTEND_PID"

echo ""
echo "  Backend:  http://localhost:8000/api/health"
echo "  Frontend: http://localhost:3000"
echo ""
echo "  Press Ctrl+C to stop both"

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; echo 'Stopped.'; exit 0" INT TERM
wait
