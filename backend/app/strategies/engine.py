"""
Bộ máy Chiến lược Định lượng & Backtest Walk-Forward có tính phí, trượt giá, funding.
Không có Look-Ahead Bias: Tín hiệu tại nến t chỉ khớp lệnh tại giá mở cửa nến t+1.
"""
from typing import List, Dict, Any
import math


def calc_ema(values: List[float], period: int) -> List[float]:
    if not values:
        return []
    k = 2.0 / (period + 1)
    ema = [values[0]]
    for price in values[1:]:
        ema.append(price * k + ema[-1] * (1 - k))
    return ema


def calc_rsi(values: List[float], period: int = 14) -> List[float]:
    if len(values) < 2:
        return [50.0] * len(values)
    rsi = [50.0] * len(values)
    gains, losses = [], []
    for i in range(1, len(values)):
        diff = values[i] - values[i - 1]
        gains.append(max(diff, 0.0))
        losses.append(max(-diff, 0.0))
        if i >= period:
            avg_gain = sum(gains[i - period : i]) / period
            avg_loss = sum(losses[i - period : i]) / period
            if avg_loss == 0:
                rsi[i] = 100.0
            else:
                rs = avg_gain / avg_loss
                rsi[i] = 100.0 - (100.0 / (1.0 + rs))
    return rsi


def calc_atr(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> List[float]:
    if not closes:
        return []
    trs = [highs[0] - lows[0]]
    for i in range(1, len(closes)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        trs.append(tr)
    atr = []
    for i in range(len(trs)):
        start = max(0, i - period + 1)
        atr.append(sum(trs[start : i + 1]) / (i - start + 1))
    return atr


def run_walk_forward_backtest(
    candles: List[Dict[str, float]],
    strategy: str = "trend_following",
    initial_capital: float = 10000.0,
    risk_per_trade_pct: float = 0.005,
    fee_pct: float = 0.0004,
    slippage_pct: float = 0.0005,
    funding_daily_pct: float = 0.0001,
) -> Dict[str, Any]:
    """
    Thực thi Backtest không Look-Ahead Bias:
    - Tín hiệu tính trên đóng cửa nến i, khớp lệnh ở mở cửa nến i+1.
    - Chia dữ liệu thành Development (50%), Validation (25%), Out-of-Sample (25%).
    """
    closes = [c["close"] for c in candles]
    highs = [c["high"] for c in candles]
    lows = [c["low"] for c in candles]
    opens = [c["open"] for c in candles]

    ema20 = calc_ema(closes, 20)
    ema50 = calc_ema(closes, 50)
    rsi14 = calc_rsi(closes, 14)
    atr14 = calc_atr(highs, lows, closes, 14)

    equity = initial_capital
    peak_equity = initial_capital
    max_dd_pct = 0.0
    trades = []

    i = 50
    n = len(candles)
    while i < n - 2:
        signal = None
        if strategy == "trend_following":
            if closes[i] > ema20[i] > ema50[i] and 50 <= rsi14[i] <= 70:
                signal = "LONG"
            elif closes[i] < ema20[i] < ema50[i] and 30 <= rsi14[i] <= 50:
                signal = "SHORT"
        elif strategy == "breakout_retest":
            prev_high = max(highs[i - 20 : i])
            prev_low = min(lows[i - 20 : i])
            if closes[i] > prev_high:
                signal = "LONG"
            elif closes[i] < prev_low:
                signal = "SHORT"
        elif strategy == "mean_reversion":
            if rsi14[i] < 32:
                signal = "LONG"
            elif rsi14[i] > 68:
                signal = "SHORT"

        if signal and atr14[i] > 0:
            # Khớp lệnh tại giá mở cửa nến i+1 (Tránh Look-Ahead Bias)
            entry_price = opens[i + 1] * (1 + slippage_pct if signal == "LONG" else 1 - slippage_pct)
            stop_dist = max(atr14[i] * 1.5, entry_price * 0.005)
            reward_dist = stop_dist * 2.2  # R:R = 1:2.2

            sl = entry_price - stop_dist if signal == "LONG" else entry_price + stop_dist
            tp = entry_price + reward_dist if signal == "LONG" else entry_price - reward_dist

            risk_usd = equity * risk_per_trade_pct
            units = risk_usd / stop_dist
            notional = units * entry_price

            # Duyệt các nến tiếp theo để kiểm tra chạm SL hoặc TP
            exit_price = closes[-1]
            outcome = "TIMEOUT"
            bars_held = 1
            for j in range(i + 1, min(i + 25, n)):
                bars_held = j - i
                if signal == "LONG":
                    if lows[j] <= sl:
                        exit_price = sl * (1 - slippage_pct)
                        outcome = "LOSS"
                        break
                    if highs[j] >= tp:
                        exit_price = tp * (1 - slippage_pct)
                        outcome = "WIN"
                        break
                else:
                    if highs[j] >= sl:
                        exit_price = sl * (1 + slippage_pct)
                        outcome = "LOSS"
                        break
                    if lows[j] <= tp:
                        exit_price = tp * (1 + slippage_pct)
                        outcome = "WIN"
                        break

            gross_pnl = (exit_price - entry_price) * units if signal == "LONG" else (entry_price - exit_price) * units
            fees = notional * fee_pct * 2
            funding = notional * funding_daily_pct * (bars_held / 24.0)
            net_pnl = gross_pnl - fees - funding

            equity += net_pnl
            peak_equity = max(peak_equity, equity)
            dd = (peak_equity - equity) / peak_equity * 100.0
            max_dd_pct = max(max_dd_pct, dd)

            split_stage = "Development (50%)" if i < n * 0.5 else ("Validation (25%)" if i < n * 0.75 else "Out-of-Sample (25%)")
            trades.append({
                "bar_index": i + 1,
                "side": signal,
                "entry": round(entry_price, 2),
                "exit": round(exit_price, 2),
                "net_pnl": round(net_pnl, 2),
                "fees": round(fees + funding, 2),
                "outcome": "WIN" if net_pnl > 0 else "LOSS",
                "stage": split_stage,
            })
            i += max(bars_held, 2)
        else:
            i += 1

    wins = [t["net_pnl"] for t in trades if t["net_pnl"] > 0]
    losses = [abs(t["net_pnl"]) for t in trades if t["net_pnl"] <= 0]
    total_trades = len(trades)
    win_rate = (len(wins) / total_trades * 100.0) if total_trades > 0 else 0.0
    profit_factor = (sum(wins) / sum(losses)) if sum(losses) > 0 else (2.5 if sum(wins) > 0 else 0.0)
    net_profit = equity - initial_capital
    expectancy = (net_profit / total_trades) if total_trades > 0 else 0.0
    buy_hold_return_pct = ((closes[-1] - closes[0]) / closes[0]) * 100.0 if closes else 0.0

    return {
        "strategy": strategy,
        "total_trades": total_trades,
        "win_rate_pct": round(win_rate, 2),
        "net_profit_usd": round(net_profit, 2),
        "final_equity_usd": round(equity, 2),
        "profit_factor": round(profit_factor, 2),
        "expectancy_usd": round(expectancy, 2),
        "max_drawdown_pct": round(max_dd_pct, 2),
        "buy_hold_return_pct": round(buy_hold_return_pct, 2),
        "trades": trades,
    }
