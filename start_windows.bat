@echo off
echo ==========================================================
echo  KHOI DONG AI AGENT TRADING PLATFORM (7 AI AGENTS MVP)
echo ==========================================================
cd /d "%~dp0backend"

if not exist ".venv" (
    echo [1/4] Dang tao moi truong ao Python (.venv)...
    python -m venv .venv
)

call .venv\Scripts\activate.bat
echo [2/4] Dang cai dat thu vien Backend (FastAPI, Uvicorn, Pydantic)...
pip install -q -r requirements.txt

echo [3/4] Dang chay 6 bai kiem thu an toan (Khoi luong 0.5%%, SL/TP, Veto)...
python tests\test_risk_and_sizing.py

echo [4/4] Dang khoi dong FastAPI Server tai http://127.0.0.1:8000 ...
start "" "%~dp0frontend\index.html"
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
pause
