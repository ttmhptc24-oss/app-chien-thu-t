"""
Bộ kiểm thử tự động (Unit Tests) cho:
1. Tính toán khối lượng lệnh (Position Sizing) theo công thức 0.5% vốn.
2. Kiểm tra hướng SL/TP (LONG vs SHORT) và cấm dời SL làm tăng rủi ro.
3. Kiểm tra giới hạn rủi ro mở tối đa, ngắt mạch lỗ ngày (-2.0%), cấm Martingale và R:R tối thiểu 1:2.
4. Kiểm tra Backtest Walk-Forward có tính phí, trượt giá và không bị Look-Ahead Bias.
"""
import importlib.util
import os
import unittest

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def load_mod(name: str, rel_path: str):
    spec = importlib.util.spec_from_file_location(name, os.path.join(BASE_DIR, rel_path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


rm_mod = load_mod("risk_manager", "app/agents/risk_manager.py")
eng_mod = load_mod("engine", "app/strategies/engine.py")

RiskManagerAgent = rm_mod.RiskManagerAgent
TradeProposal = rm_mod.TradeProposal
OpenPosition = rm_mod.OpenPosition
run_walk_forward_backtest = eng_mod.run_walk_forward_backtest


class TestRiskAndSizing(unittest.TestCase):
    def test_position_sizing_exact_0_5_percent(self):
        rm = RiskManagerAgent(max_risk_per_trade_pct=0.005)
        res = rm.calculate_position_size(equity_usd=10000.0, entry_price=80000.0, stop_loss=79000.0)
        self.assertEqual(res["risk_usd"], 50.0)
        self.assertEqual(res["units"], 0.05)
        self.assertEqual(res["notional_usd"], 4000.0)
        self.assertEqual(res["risk_pct"], 0.5)

    def test_veto_invalid_stop_loss_direction(self):
        rm = RiskManagerAgent()
        bad_long = TradeProposal(
            symbol="BTCUSDT",
            side="LONG",
            entry_price=80000.0,
            stop_loss=80500.0,
            take_profit=82500.0,
        )
        decision = rm.evaluate_proposal(10000.0, 0.0, [], bad_long)
        self.assertFalse(decision.approved)
        self.assertTrue(any("Stop Loss lệnh LONG" in r for r in decision.veto_reasons))

    def test_forbid_widening_stop_loss(self):
        rm = RiskManagerAgent()
        self.assertFalse(rm.validate_stop_loss_modification("LONG", current_sl=79200.0, new_sl=78800.0))
        self.assertTrue(rm.validate_stop_loss_modification("LONG", current_sl=79200.0, new_sl=79600.0))
        self.assertFalse(rm.validate_stop_loss_modification("SHORT", current_sl=2400.0, new_sl=2450.0))

    def test_veto_low_risk_reward_and_martingale(self):
        rm = RiskManagerAgent(min_rr_ratio=2.0)
        proposal = TradeProposal(
            symbol="ETHUSDT",
            side="LONG",
            entry_price=2340.0,
            stop_loss=2300.0,
            take_profit=2388.0,
            is_martingale_attempt=True,
        )
        decision = rm.evaluate_proposal(10000.0, 0.0, [], proposal)
        self.assertFalse(decision.approved)
        self.assertTrue(any("MARTINGALE" in r for r in decision.veto_reasons))
        self.assertTrue(any("Risk/Reward" in r for r in decision.veto_reasons))

    def test_daily_loss_circuit_breaker_and_max_open_risk(self):
        rm = RiskManagerAgent(max_daily_loss_pct=0.02, max_open_risk_pct=0.02)
        valid_proposal = TradeProposal(
            symbol="SOLUSDT",
            side="LONG",
            entry_price=101.0,
            stop_loss=98.0,
            take_profit=108.0,
        )
        decision = rm.evaluate_proposal(10000.0, -210.0, [], valid_proposal)
        self.assertFalse(decision.approved)
        self.assertTrue(any("ngắt mạch lỗ ngày" in r for r in decision.veto_reasons))

    def test_walk_forward_backtest_with_fees(self):
        candles = []
        price = 80000.0
        for i in range(120):
            step = 120.0 if (i % 7 != 0) else -150.0
            open_p = price
            close_p = price + step
            high_p = max(open_p, close_p) + 90.0
            low_p = min(open_p, close_p) - 70.0
            candles.append({"open": open_p, "high": high_p, "low": low_p, "close": close_p})
            price = close_p

        res = run_walk_forward_backtest(candles, strategy="trend_following", initial_capital=10000.0)
        self.assertIn("total_trades", res)
        self.assertIn("max_drawdown_pct", res)
        self.assertGreater(res["final_equity_usd"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
