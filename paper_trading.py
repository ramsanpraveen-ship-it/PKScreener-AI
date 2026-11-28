"""Deterministic helpers for a manual, simulated NSE cash-equity journal."""


def validate_paper_entry(entry_price, stop_loss, quantity, open_positions, deployed, aggregate_open_risk=0):
    from risk_manager import (
        MAX_RISK_PER_TRADE, MAX_POSITION_VALUE, MAX_OPEN_POSITIONS,
        MAX_DEPLOYMENT, TOTAL_CAPITAL, MAX_AGGREGATE_OPEN_RISK,
    )

    if stop_loss >= entry_price:
        raise ValueError("Stop loss must be below entry price for a long cash position")
    risk = (entry_price - stop_loss) * quantity
    investment = entry_price * quantity
    if risk > MAX_RISK_PER_TRADE:
        raise ValueError("Paper trade exceeds the ₹500 planned risk limit")
    if aggregate_open_risk + risk > MAX_AGGREGATE_OPEN_RISK:
        raise ValueError("Paper trade exceeds the ₹1,500 aggregate open risk limit")
    if investment > MAX_POSITION_VALUE:
        raise ValueError("Paper trade exceeds the ₹20,000 per-position limit")
    if open_positions >= MAX_OPEN_POSITIONS:
        raise ValueError("Maximum three open paper positions reached")
    if deployed + investment > min(MAX_DEPLOYMENT, TOTAL_CAPITAL):
        raise ValueError("Paper trades would exceed the deployment limit")
    return {"planned_risk": risk, "investment": investment}


def summarize_paper_trades(trades):
    """Summarize only realized, explicitly closed simulations (before costs)."""
    closed = [trade for trade in trades if trade.get("status") == "CLOSED"]
    pnls = [
        (float(trade["exit_price"]) - float(trade["entry_price"])) * int(trade["quantity"])
        for trade in closed
    ]
    wins = [pnl for pnl in pnls if pnl > 0]
    losses = [pnl for pnl in pnls if pnl < 0]
    total_loss = abs(sum(losses))
    gross_profit = sum(wins)
    return {
        "closed_trades": len(closed),
        "open_trades": sum(trade.get("status") == "OPEN" for trade in trades),
        "realized_pnl_before_costs": sum(pnls),
        "win_rate_percent": (100 * len(wins) / len(closed)) if closed else None,
        "profit_factor": (gross_profit / total_loss) if total_loss else (None if not wins else "infinite"),
        "costs_included": False,
        "live_orders_placed": False,
    }
