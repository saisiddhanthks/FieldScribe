#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  python3 -m venv .venv
  . .venv/bin/activate
  pip install --upgrade pip
  pip install -r backend/requirements.txt
  pip install -r backend/requirements-hub.txt || true
  pip install -r backend/requirements-asr.txt || echo "faster-whisper failed to install; typing still works"
else
  . .venv/bin/activate
fi
[ -f backend/.env ] || cp backend/.env.example backend/.env
python run.py
