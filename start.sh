#!/usr/bin/env bash
set -euo pipefail

echo ">>> Installing Python dependencies..."
pip install -r requirements.txt

# Make sure Playwright browsers are available
export PLAYWRIGHT_BROWSERS_PATH=/opt/render/.cache/ms-playwright
echo ">>> Installing Playwright Chromium browser..."
python -m playwright install chromium

# Run your FastAPI app
PORT=${PORT:-10000}
echo ">>> Starting FastAPI (Uvicorn) on port $PORT"
exec uvicorn app.main:app --host 0.0.0.0 --port $PORT
