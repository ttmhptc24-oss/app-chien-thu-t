#!/usr/bin/env bash
set -e
echo "=========================================================="
echo " KHOI DONG AI AGENT TRADING PLATFORM (7 AI AGENTS MVP)"
echo "=========================================================="

cd "$(dirname "$0")/backend"
if [ ! -d ".venv" ]; then
  echo "[1/4] Dang tao moi truong ao Python (.venv)..."
  python3 -m venv .venv
fi

source .venv/bin/activate
echo "[2/4] Dang cai dat thu vien Backend (FastAPI, Uvicorn, Pydantic)..."
pip install -q --upgrade pip
pip install -q -r requirements.txt

echo "[3/4] Dang chay 6 bai kiem thu an toan (Khối lượng 0.5%, SL/TP, Veto)..."
python3 tests/test_risk_and_sizing.py

echo "[4/4] Dang khoi dong FastAPI Server tai http://127.0.0.1:8000 ..."
echo "      Ban hay mo file frontend/index.html bang trinh duyet Chrome/Edge!"
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
