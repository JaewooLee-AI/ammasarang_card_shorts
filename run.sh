#!/usr/bin/env bash
# Anmasarang AI Content Studio Launch Script
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
cd "$DIR"

if [ -f ".venv/bin/python3" ]; then
    PYTHON_BIN=".venv/bin/python3"
else
    PYTHON_BIN="python3"
fi

echo "🚀 Starting Anmasarang AI Studio (Flet 1.0.4)..."
"$PYTHON_BIN" main.py
