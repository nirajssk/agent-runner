#!/usr/bin/env bash
# Start both backend and frontend dev servers

# Check for Python
if ! command -v python &>/dev/null && ! command -v python3 &>/dev/null; then
  echo "Python not found. Install Python 3.11+ and try again."
  exit 1
fi

PYTHON=$(command -v python3 || command -v python)

# Backend setup
echo "==> Setting up backend..."
cd "$(dirname "$0")/backend"
if [ ! -d ".venv" ]; then
  $PYTHON -m venv .venv
  echo "   Virtual env created"
fi
source .venv/Scripts/activate 2>/dev/null || source .venv/bin/activate
pip install -r requirements.txt -q
echo "   Dependencies installed"

# Start backend in background
uvicorn main:app --reload --port 8000 &
BACKEND_PID=$!
echo "   Backend started (pid $BACKEND_PID) at http://localhost:8000"

# Frontend setup
echo "==> Setting up frontend..."
cd "$(dirname "$0")/frontend"
if [ ! -d "node_modules" ]; then
  npm install -q
  echo "   node_modules installed"
fi

# Start frontend
echo "   Frontend starting at http://localhost:5173"
npm run dev &
FRONTEND_PID=$!

echo ""
echo "==> Agent Runner is up!"
echo "    Dashboard: http://localhost:5173"
echo "    API:       http://localhost:8000"
echo ""
echo "Press Ctrl+C to stop both servers."

# Cleanup on exit
trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" INT TERM
wait
