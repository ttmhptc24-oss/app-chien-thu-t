"""
FastAPI Backend cho AI Agent Trading Platform (7 AI Agents + Risk Manager Veto + Backtest Engine)
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from app.agents.risk_manager import RiskManagerAgent, TradeProposal, OpenPosition
from app.strategies.engine import run_walk_forward_backtest

app = FastAPI(
    title="AI Agent Trading Platform API",
    description="Hệ thống 7 AI Agent định lượng, Quản trị rủi ro Veto 0.5% và Backtest Walk-Forward",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

risk_manager = RiskManagerAgent()


class SizeRequest(BaseModel):
    equity_usd: float
    entry_price: float
    stop_loss: float
    custom_risk_pct: Optional[float] = 0.005


@app.get("/api/v1/health")
def health_check():
    return {
        "status": "OK",
        "mode": "PAPER_TRADING_ONLY",
        "live_trading_locked": True,
        "emergency_stop": risk_manager.emergency_stop_active,
        "agents_online": 7,
    }


@app.post("/api/v1/risk/calculate-size")
def api_calculate_size(req: SizeRequest):
    try:
        return risk_manager.calculate_position_size(
            req.equity_usd, req.entry_price, req.stop_loss, req.custom_risk_pct
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
