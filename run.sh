#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="/Users/riverpease/Downloads/Fall2025/tmc/tmc"
cd "$PROJECT_DIR"

# Ensure Python 3.11 venv exists
if [ ! -d "venv" ]; then
  if ! command -v python3.11 >/dev/null 2>&1; then
    echo "Python 3.11 is required. Please install it (e.g., brew install python@3.11)."
    exit 1
  fi
  python3.11 -m venv venv
fi

source venv/bin/activate
python -V

# Install dependencies
pip install --upgrade pip setuptools wheel
pip install -r requirements.txt

# Required env vars
export FLASK_SECRET_KEY="dev"
export GOOGLE_APPLICATION_CREDENTIALS="$PROJECT_DIR/dolphin-393123-2ac6bf25dfab.json"

# Ensure placeholder code file exists
if [ ! -f "static/code_file.js" ]; then
  echo "// code will appear here after processing an image" > static/code_file.js
fi

# Start app
python app.py


