"""
Agent 5 — Giám Đốc Quản Trị Rủi Ro (Risk Manager Agent)
Có quyền phủ quyết (VETO) mọi giao dịch vi phạm quy tắc an toàn vốn.
"""
from dataclasses import dataclass
from typing import List, Optional, Dict, Any


@dataclass
class TradeProposal:
    symbol: str
    side: str  # "LONG" or "SHORT"
    entry_price: float
    stop_loss: float
    take_profit: float
    atr: float = 0.0
    strategy_name: str = "Trend Following"
    is_martingale_attempt: bool = False
    liquidity_usd_24h: float = 1_000_000_000.0


@dataclass
class OpenPosition:
    symbol: str
    side: str
    entry_price: float
    stop_loss: float
    take_profit: float
    quantity: float
    risk_usd: float


@dataclass
class RiskDecision:
    approved: bool
    veto_reasons: List[str]
    position_size_units: float
    notional_value_usd: float
    risk_amount_usd: float
    risk_percent: float
    reward_risk_ratio: float
    estimated_fee_usd: float
    estimated_slippage_usd: float
    net_expected_rr: float


class RiskManagerAgent:
    def __init__(
        self,
        max_risk_per_trade_pct: float = 0.005,   # 0.5% vốn mỗi lệnh
        max_open_risk_pct: float = 0.02,         # 2.0% tổng rủi ro mở tối đa
        max_daily_loss_pct: float = 0.02,        # -2.0% ngắt mạch lỗ ngày
        min_rr_ratio: float = 2.0,               # R:R tối thiểu 1:2
        taker_fee_pct: float = 0.0004,           # 0.04% phí Taker
        slippage_pct: float = 0.0005,            # 0.05% trượt giá dự kiến
        min_liquidity_24h_usd: float = 50_000_000.0,
    ):
        self.max_risk_per_trade_pct = max_risk_per_trade_pct
        self.max_open_risk_pct = max_open_risk_pct
        self.max_daily_loss_pct = max_daily_loss_pct
        self.min_rr_ratio = min_rr_ratio
        self.taker_fee_pct = taker_fee_pct
        self.slippage_pct = slippage_pct
        self.min_liquidity_24h_usd = min_liquidity_24h_usd
        self.emergency_stop_active = False

    def calculate_position_size(
        self, equity_usd: float, entry_price: float, stop_loss: float, custom_risk_pct: Optional[float] = None
    ) -> Dict[str, float]:
        """
        Tính khối lượng lệnh từ số vốn chấp nhận rủi ro và khoảng cách Stop Loss.
        Công thức: Khối lượng = (Vốn * %Rủi_ro) / |Entry - StopLoss|
        """
        if equity_usd <= 0 or entry_price <= 0 or stop_loss <= 0:
            raise ValueError("Vốn, giá vào lệnh và Stop Loss phải lớn hơn 0.")
        stop_distance = abs(entry_price - stop_loss)
        if stop_distance <= 1e-9:
            raise ValueError("Khoảng cách Stop Loss không hợp lệ (bằng 0).")

        risk_pct = min(custom_risk_pct or self.max_risk_per_trade_pct, self.max_risk_per_trade_pct)
        risk_usd = equity_usd * risk_pct
        units = risk_usd / stop_distance
        notional_usd = units * entry_price
        return {
            "units": round(units, 6),
            "notional_usd": round(notional_usd, 2),
            "risk_usd": round(risk_usd, 2),
            "risk_pct": round(risk_pct * 100, 4),
            "stop_distance": round(stop_distance, 4),
        }

    def validate_stop_loss_modification(
        self, side: str, current_sl: float, new_sl: float
    ) -> bool:
        """
        Không tự ý dời Stop Loss theo hướng làm tăng rủi ro.
        - Lệnh LONG: new_sl phải >= current_sl (chỉ được dời lên).
        - Lệnh SHORT: new_sl phải <= current_sl (chỉ được dời xuống).
        """
        side_up = side.upper()
        if side_up == "LONG":
            return new_sl >= current_sl
        elif side_up == "SHORT":
            return new_sl <= current_sl
        return False

    def evaluate_proposal(
        self,
        equity_usd: float,
        daily_pnl_usd: float,
        open_positions: List[OpenPosition],
        proposal: TradeProposal,
        requested_risk_pct: float = 0.005,
    ) -> RiskDecision:
        veto_reasons: List[str] = []

        if self.emergency_stop_active:
            veto_reasons.append("Hệ thống đang bật DỪNG KHẨN CẤP (Emergency Stop).")

        if requested_risk_pct > self.max_risk_per_trade_pct + 1e-9:
            veto_reasons.append(
                f"Rủi ro yêu cầu ({requested_risk_pct*100:.2f}%) vượt trần 0.50% vốn."
            )

        if proposal.is_martingale_attempt:
            veto_reasons.append("CẤM MARTINGALE: Phát hiện hành vi nhồi lệnh gấp thếp gỡ lỗ.")

        # Kiểm tra giới hạn lỗ ngày (-2.0%)
        daily_loss_limit_usd = -abs(equity_usd * self.max_daily_loss_pct)
        if daily_pnl_usd <= daily_loss_limit_usd:
            veto_reasons.append(
                f"Chạm ngưỡng ngắt mạch lỗ ngày ({daily_pnl_usd:.2f} USD <= {daily_loss_limit_usd:.2f} USD)."
            )

        # Kiểm tra hướng Stop Loss & Take Profit
        side = proposal.side.upper()
        if side == "LONG":
            if proposal.stop_loss >= proposal.entry_price:
                veto_reasons.append("Stop Loss lệnh LONG phải thấp hơn giá vào lệnh.")
            if proposal.take_profit <= proposal.entry_price:
                veto_reasons.append("Take Profit lệnh LONG phải cao hơn giá vào lệnh.")
        elif side == "SHORT":
            if proposal.stop_loss <= proposal.entry_price:
                veto_reasons.append("Stop Loss lệnh SHORT phải cao hơn giá vào lệnh.")
            if proposal.take_profit >= proposal.entry_price:
                veto_reasons.append("Take Profit lệnh SHORT phải thấp hơn giá vào lệnh.")
        else:
            veto_reasons.append(f"Hướng giao dịch không hợp lệ: {proposal.side}")

        # Kiểm tra xung đột vị thế trùng lặp
        for pos in open_positions:
            if pos.symbol == proposal.symbol:
                veto_reasons.append(f"Đã có vị thế đang mở cho tài sản {proposal.symbol}.")
                break

        # Kiểm tra thanh khoản
        if proposal.liquidity_usd_24h < self.min_liquidity_24h_usd:
            veto_reasons.append("Thanh khoản 24h không đạt ngưỡng an toàn tối thiểu.")

        stop_dist = abs(proposal.entry_price - proposal.stop_loss)
        reward_dist = abs(proposal.take_profit - proposal.entry_price)
        if stop_dist <= 1e-9:
            veto_reasons.append("Khoảng cách Stop Loss bằng 0.")
            return RiskDecision(False, veto_reasons, 0, 0, 0, 0, 0, 0, 0, 0)

        rr_ratio = reward_dist / stop_dist
        if rr_ratio < self.min_rr_ratio - 1e-9:
            veto_reasons.append(
                f"Tỷ lệ Risk/Reward ({rr_ratio:.2f}) thấp hơn mức tối thiểu 1:{self.min_rr_ratio:.1f}."
            )

        effective_risk_pct = min(requested_risk_pct, self.max_risk_per_trade_pct)
        risk_usd = equity_usd * effective_risk_pct
        units = risk_usd / stop_dist
        notional_usd = units * proposal.entry_price

        # Kiểm tra tổng rủi ro các vị thế đang mở
        current_open_risk_usd = sum(p.risk_usd for p in open_positions)
        max_open_risk_usd = equity_usd * self.max_open_risk_pct
        if current_open_risk_usd + risk_usd > max_open_risk_usd + 1e-6:
            veto_reasons.append(
                f"Tổng rủi ro mở ({current_open_risk_usd + risk_usd:.2f} USD) vượt trần {self.max_open_risk_pct*100:.1f}% vốn."
            )

        # Tính phí 2 chiều (mở + đóng) và trượt giá
        est_fee_usd = notional_usd * self.taker_fee_pct * 2
        est_slip_usd = notional_usd * self.slippage_pct * 2
        gross_reward_usd = units * reward_dist
        net_reward_usd = max(0.0, gross_reward_usd - est_fee_usd - est_slip_usd)
        total_effective_risk_usd = risk_usd + est_fee_usd + est_slip_usd
        net_rr = net_reward_usd / total_effective_risk_usd if total_effective_risk_usd > 0 else 0.0

        return RiskDecision(
            approved=(len(veto_reasons) == 0),
            veto_reasons=veto_reasons,
            position_size_units=round(units, 6),
            notional_value_usd=round(notional_usd, 2),
            risk_amount_usd=round(risk_usd, 2),
            risk_percent=round(effective_risk_pct * 100, 4),
            reward_risk_ratio=round(rr_ratio, 2),
            estimated_fee_usd=round(est_fee_usd, 2),
            estimated_slippage_usd=round(est_slip_usd, 2),
            net_expected_rr=round(net_rr, 2),
        )
