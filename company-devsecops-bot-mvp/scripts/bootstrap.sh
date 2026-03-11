#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

if [[ ! -f .env ]]; then
  cp .env.example .env
fi

echo "Bootstrap done. Activate with: source .venv/bin/activate"
