"""Idempotent daily forward-paper simulator; never places broker orders."""
import csv
import sqlite3
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from market_data import _nse_eq_bar
from nse_calendar import is_nse_trading_day
from risk_manager import (MAX_DEPLOYMENT, MAX_OPEN_POSITIONS,
                          MAX_POSITION_VALUE, MAX_RISK_PER_TRADE)

DB_PATH = Path(__file__).resolve().parent / "data" / "forward_paper.sqlite3"
SLIPPAGE_BPS_PER_SIDE = 5.0
AUTO_CONFIDENCE_THRESHOLD = 90.0


def _connect(path=DB_PATH):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=30)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("CREATE TABLE IF NOT EXISTS paper_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    db.execute("INSERT OR IGNORE INTO paper_settings(key,value) VALUES('mode','ask')")
    db.execute("""CREATE TABLE IF NOT EXISTS paper_sessions (
        session_date TEXT PRIMARY KEY, scan_file TEXT NOT NULL, processed_at TEXT DEFAULT CURRENT_TIMESTAMP,
        queued INTEGER NOT NULL DEFAULT 0, opened INTEGER NOT NULL DEFAULT 0, closed INTEGER NOT NULL DEFAULT 0
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS forward_trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT NOT NULL, signal_date TEXT NOT NULL,
        signal_rank REAL NOT NULL DEFAULT 0, confidence_pct REAL NOT NULL DEFAULT 0, reference_close REAL NOT NULL,
        stop_loss REAL NOT NULL, target_price REAL NOT NULL,
        status TEXT NOT NULL, quantity INTEGER NOT NULL DEFAULT 0,
        planned_quantity INTEGER NOT NULL DEFAULT 0,
        entry_date TEXT, entry_price REAL, exit_date TEXT, exit_price REAL,
        exit_reason TEXT, fees REAL NOT NULL DEFAULT 0, net_pnl REAL,
        mark_price REAL, unrealized_pnl REAL, holding_sessions INTEGER NOT NULL DEFAULT 0,
        UNIQUE(symbol, signal_date)
    )""")
    db.commit()
    return db


def get_mode(db_path=DB_PATH):
    db = _connect(db_path)
    try:
        row = db.execute("SELECT value FROM paper_settings WHERE key='mode'").fetchone()
        return row[0] if row else "ask"
    finally:
        db.close()


def set_mode(mode, db_path=DB_PATH):
    if mode not in {"manual", "ask", "auto"}:
        raise ValueError("Mode must be manual, ask, or auto")
    db = _connect(db_path)
    try:
        db.execute("INSERT OR REPLACE INTO paper_settings(key,value) VALUES('mode',?)", (mode,))
        if mode == "manual":
            db.execute("UPDATE forward_trades SET status='PENDING_APPROVAL' WHERE status='QUEUED'")
        elif mode == "ask":
            db.execute("UPDATE forward_trades SET status='PENDING_APPROVAL' WHERE status='QUEUED' AND confidence_pct < ?", (AUTO_CONFIDENCE_THRESHOLD,))
            db.execute("UPDATE forward_trades SET status='QUEUED' WHERE status='PENDING_APPROVAL' AND confidence_pct >= ?", (AUTO_CONFIDENCE_THRESHOLD,))
        else:
            db.execute("UPDATE forward_trades SET status='QUEUED' WHERE status='PENDING_APPROVAL'")
        db.commit()
    finally:
        db.close()
    return mode


def approve_signal(trade_id, db_path=DB_PATH):
    db = _connect(db_path)
    try:
        cursor = db.execute("UPDATE forward_trades SET status='QUEUED' WHERE id=? AND status='PENDING_APPROVAL'", (trade_id,))
        db.commit()
        return cursor.rowcount == 1
    finally:
        db.close()


def _number(row, key):
    try:
        value = float(row.get(key, ""))
        return value if pd.notna(value) else None
    except (TypeError, ValueError):
        return None


def _session_bar(symbol, day):
    # Use exact-date raw NSE EQ OHLC for fills and P&L. Yahoo's auto-adjusted
    # history can revise past prices after dividends and split events.
    frame, _source = _nse_eq_bar(symbol, pd.Timestamp(day).date())
    if len(frame) != 1 or frame.empty:
        raise ValueError(f"{symbol}: expected one official EQ candle for {day}")
    return frame.iloc[0]


def _next_nse_session(day):
    candidate = pd.Timestamp(day).date() + timedelta(days=1)
    while not is_nse_trading_day(candidate):
        candidate += timedelta(days=1)
    return candidate


def _close_trade(db, trade, day, raw_price, reason):
    slip = SLIPPAGE_BPS_PER_SIDE / 10_000
    exit_price = float(raw_price) * (1 - slip)
    entry_price = float(trade["entry_price"])
    qty = int(trade["quantity"])
    # Statutory NSE delivery charges, with no assumed broker brokerage.
    from backtest_engine import BacktestConfig, _fee_rate
    cfg = BacktestConfig(slippage_bps_per_side=SLIPPAGE_BPS_PER_SIDE)
    exit_fees = exit_price * qty * _fee_rate(pd.Timestamp(day), "sell", cfg)
    entry_fees = float(trade["fees"])
    net = (exit_price - entry_price) * qty - entry_fees - exit_fees
    db.execute("""UPDATE forward_trades SET status='CLOSED', exit_date=?, exit_price=?,
        exit_reason=?, fees=?, net_pnl=?, holding_sessions=? WHERE id=?""",
        (str(day), round(exit_price, 4), reason, round(entry_fees + exit_fees, 2),
         round(net, 2), int(trade["holding_sessions"]), trade["id"]))


def process_fresh_scan(results_file, expected_session, metadata_file=None, db_path=DB_PATH):
    """Advance one completed session exactly once; stale scans are rejected."""
    results_file = Path(results_file)
    expected = str(expected_session)
    if metadata_file:
        import json
        meta = json.loads(Path(metadata_file).read_text(encoding="utf-8"))
        dates = meta.get("stock_dates") or {}
        if (meta.get("freshness_status") != "FRESH"
                or meta.get("expected_session") != expected
                or meta.get("benchmark_date") != expected
                or meta.get("has_analysis_errors") is not False
                or not dates or any(str(v) != expected for v in dates.values())):
            raise ValueError("Freshness gate closed; paper book did not advance")
    with results_file.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if not rows or any(row.get("analysis_date") != expected for row in rows):
        raise ValueError("Scan rows are empty or do not match the expected session")

    db = _connect(db_path)
    try:
        if db.execute("SELECT 1 FROM paper_sessions WHERE session_date=?", (expected,)).fetchone():
            return {"status": "ALREADY_PROCESSED", "session_date": expected}
        # Advance existing open positions using the exact completed daily candle.
        closed = opened = 0
        open_trades = db.execute("SELECT * FROM forward_trades WHERE status='OPEN'").fetchall()
        for trade in open_trades:
            bar = _session_bar(trade["symbol"], expected)
            op, hi, lo, cl = map(float, (bar["Open"], bar["High"], bar["Low"], bar["Close"]))
            stop, target = float(trade["stop_loss"]), float(trade["target_price"])
            sessions_held = int(trade["holding_sessions"]) + 1
            reason = price = None
            if op <= stop:
                reason, price = "STOP_GAP", op
            elif op >= target:
                reason, price = "TARGET_GAP", op
            elif lo <= stop and hi >= target:
                reason, price = "STOP_BOTH_TOUCHED", stop
            elif lo <= stop:
                reason, price = "STOP", stop
            elif hi >= target:
                reason, price = "TARGET", target
            elif sessions_held >= 20:
                reason, price = "TIME_EXIT_20_SESSIONS", cl
            mark = cl * (1 - SLIPPAGE_BPS_PER_SIDE / 10_000)
            from backtest_engine import BacktestConfig, _fee_rate
            cfg = BacktestConfig(slippage_bps_per_side=SLIPPAGE_BPS_PER_SIDE)
            estimated_sell_fee = mark * int(trade["quantity"]) * _fee_rate(pd.Timestamp(expected), "sell", cfg)
            unrealized = (mark - float(trade["entry_price"])) * int(trade["quantity"]) - float(trade["fees"]) - estimated_sell_fee
            db.execute("UPDATE forward_trades SET holding_sessions=?,mark_price=?,unrealized_pnl=? WHERE id=?",
                       (sessions_held, round(mark, 4), round(unrealized, 2), trade["id"]))
            if reason:
                trade = dict(trade)
                trade["holding_sessions"] = sessions_held
                _close_trade(db, trade, expected, price, reason)
                closed += 1

        # Execute prior-session confirmed signals at today's open. Rank high RS first.
        queued = db.execute("SELECT * FROM forward_trades WHERE status='QUEUED' AND signal_date<? ORDER BY signal_rank DESC, symbol", (expected,)).fetchall()
        active = db.execute("SELECT * FROM forward_trades WHERE status='OPEN'").fetchall()
        deployed = sum(float(t["entry_price"]) * int(t["quantity"]) for t in active)
        for trade in queued:
            signal_day = pd.Timestamp(trade["signal_date"]).date()
            if _next_nse_session(signal_day).isoformat() != expected:
                db.execute("UPDATE forward_trades SET status='CANCELLED', exit_reason='MISSED_NEXT_SESSION_ENTRY' WHERE id=?", (trade["id"],))
                continue
            bar = _session_bar(trade["symbol"], expected)
            op = float(bar["Open"])
            entry = op * (1 + SLIPPAGE_BPS_PER_SIDE / 10_000)
            ref, stop = float(trade["reference_close"]), float(trade["stop_loss"])
            target = float(trade["target_price"])
            if entry > ref * 1.05 or entry <= stop or entry >= target or len(active) >= MAX_OPEN_POSITIONS:
                db.execute("UPDATE forward_trades SET status='CANCELLED', exit_reason=? WHERE id=?",
                           ("GAP_OR_CAPACITY_RULE", trade["id"]))
                continue
            from backtest_engine import BacktestConfig, _fee_rate
            cfg = BacktestConfig(slippage_bps_per_side=SLIPPAGE_BPS_PER_SIDE)
            buy_fee_rate = _fee_rate(pd.Timestamp(expected), "buy", cfg)
            sell_fee_rate = _fee_rate(pd.Timestamp(expected), "sell", cfg)
            expected_stop = stop * (1 - SLIPPAGE_BPS_PER_SIDE / 10_000)
            risk_per_share = entry * (1 + buy_fee_rate) - expected_stop * (1 - sell_fee_rate)
            room = min(MAX_POSITION_VALUE, MAX_DEPLOYMENT - deployed)
            qty = min(int(MAX_RISK_PER_TRADE // risk_per_share), int(room // (entry * (1 + buy_fee_rate))))
            if qty < 1:
                db.execute("UPDATE forward_trades SET status='CANCELLED', exit_reason='RISK_OR_CAPITAL_CAP' WHERE id=?", (trade["id"],))
                continue
            fee = entry * qty * buy_fee_rate
            close = float(bar["Close"])
            mark = close * (1 - SLIPPAGE_BPS_PER_SIDE / 10_000)
            estimated_sell_fee = mark * qty * sell_fee_rate
            unrealized = (mark - entry) * qty - fee - estimated_sell_fee
            db.execute("UPDATE forward_trades SET status='OPEN', quantity=?, entry_date=?, entry_price=?, fees=?,mark_price=?,unrealized_pnl=?,holding_sessions=1 WHERE id=?",
                       (qty, expected, round(entry, 4), round(fee, 2), round(mark, 4), round(unrealized, 2), trade["id"]))
            deployed += qty * entry + fee
            active.append({"symbol": trade["symbol"]})
            opened += 1
            # Include entry-session intraday movement in the paper lifecycle.
            hi, lo, close = float(bar["High"]), float(bar["Low"]), float(bar["Close"])
            exit_reason = exit_price = None
            if lo <= stop and hi >= target:
                exit_reason, exit_price = "STOP_BOTH_TOUCHED", stop
            elif lo <= stop:
                exit_reason, exit_price = "STOP", stop
            elif hi >= target:
                exit_reason, exit_price = "TARGET", target
            if exit_reason:
                position = {"id": trade["id"], "entry_price": round(entry, 4), "quantity": qty,
                            "fees": round(fee, 2), "holding_sessions": 1}
                _close_trade(db, position, expected, exit_price, exit_reason)
                closed += 1

        # Record only confirmed signals with valid deterministic stop/target levels.
        queued_count = 0
        for row in rows:
            if row.get("candidate_status") != "BREAKOUT_CONFIRMED":
                continue
            adjusted_entry, adjusted_stop, adjusted_target = (_number(row, k) for k in ("entry_reference", "stop_loss", "target_price"))
            rs = _number(row, "relative_strength") or 0.0
            confidence = _number(row, "confidence_pct") or 0.0
            if not adjusted_entry or not adjusted_stop or not adjusted_target:
                continue
            raw_bar = _session_bar(row["symbol"], expected)
            adjusted_close = _number(row, "latest_price")
            raw_close = float(raw_bar["Close"])
            if not adjusted_close or adjusted_close <= 0:
                continue
            adjustment_scale = raw_close / adjusted_close
            entry = raw_close
            stop = float(adjusted_stop) * adjustment_scale
            target = float(adjusted_target) * adjustment_scale
            if not (0 < stop < entry < target):
                continue
            from backtest_engine import BacktestConfig, _fee_rate
            cfg = BacktestConfig(slippage_bps_per_side=SLIPPAGE_BPS_PER_SIDE)
            buy_rate = _fee_rate(pd.Timestamp(expected), "buy", cfg)
            sell_rate = _fee_rate(pd.Timestamp(expected), "sell", cfg)
            stop_fill = stop * (1 - SLIPPAGE_BPS_PER_SIDE / 10_000)
            risk_per_share = entry * (1 + buy_rate) - stop_fill * (1 - sell_rate)
            planned_qty = min(int(MAX_RISK_PER_TRADE // risk_per_share), int(MAX_POSITION_VALUE // (entry * (1 + buy_rate))))
            if planned_qty < 1:
                continue
            mode_row = db.execute("SELECT value FROM paper_settings WHERE key='mode'").fetchone()
            mode = mode_row[0] if mode_row else "ask"
            status = "QUEUED" if mode == "auto" or (mode == "ask" and confidence >= AUTO_CONFIDENCE_THRESHOLD) else "PENDING_APPROVAL"
            cur = db.execute("""INSERT OR IGNORE INTO forward_trades
                (symbol,signal_date,signal_rank,confidence_pct,reference_close,stop_loss,target_price,planned_quantity,status)
                VALUES(?,?,?,?,?,?,?,?,?)""",
                (row["symbol"], expected, rs, confidence, entry, stop, target, planned_qty, status))
            queued_count += cur.rowcount
        db.execute("INSERT INTO paper_sessions(session_date,scan_file,queued,opened,closed) VALUES(?,?,?,?,?)",
                   (expected, results_file.name, queued_count, opened, closed))
        db.commit()
        return {"status": "PROCESSED", "session_date": expected,
                "new_signals_queued": queued_count, "trades_opened": opened,
                "trades_closed": closed, "orders_placed": False}
    finally:
        db.close()


def get_forward_book(db_path=DB_PATH):
    db = _connect(db_path)
    try:
        trades = [dict(r) for r in db.execute("SELECT * FROM forward_trades ORDER BY signal_date DESC, id DESC")]
        sessions = [dict(r) for r in db.execute("SELECT * FROM paper_sessions ORDER BY session_date DESC")]
    finally:
        db.close()
    closed = [t for t in trades if t["status"] == "CLOSED"]
    wins = [float(t["net_pnl"]) for t in closed if float(t["net_pnl"] or 0) > 0]
    losses = [float(t["net_pnl"]) for t in closed if float(t["net_pnl"] or 0) < 0]
    gross_loss = abs(sum(losses))
    avg_win = sum(wins) / len(wins) if wins else None
    avg_loss = gross_loss / len(losses) if losses else None
    equity = 100_000.0
    peak = equity
    max_drawdown = 0.0
    for trade in sorted(closed, key=lambda t: (t["exit_date"] or "", t["id"])):
        equity += float(trade["net_pnl"] or 0)
        peak = max(peak, equity)
        if peak > 0:
            max_drawdown = max(max_drawdown, (peak - equity) / peak * 100)
    summary = {
        "sessions_processed": len(sessions), "queued_trades": sum(t["status"] == "QUEUED" for t in trades),
        "open_trades": sum(t["status"] == "OPEN" for t in trades), "closed_trades": len(closed),
        "win_rate_percent": 100 * len(wins) / len(closed) if closed else None,
        "profit_factor": sum(wins) / gross_loss if gross_loss else ("infinite" if wins else None),
        "average_win": round(avg_win, 2) if avg_win is not None else None,
        "average_loss": round(avg_loss, 2) if avg_loss is not None else None,
        "average_win_loss_ratio": round(avg_win / avg_loss, 3) if avg_win is not None and avg_loss else None,
        "max_drawdown_percent": round(max_drawdown, 3),
        "net_realized_pnl": round(sum(float(t["net_pnl"] or 0) for t in closed), 2),
        "unrealized_pnl": round(sum(float(t["unrealized_pnl"] or 0) for t in trades if t["status"] == "OPEN"), 2),
        "costs_included": True, "slippage_bps_per_side": SLIPPAGE_BPS_PER_SIDE,
        "brokerage_assumption": "₹0; actual brokerage varies by broker",
        "live_orders_placed": False, "mode": get_mode(db_path),
    }
    latest_session = sessions[0]["session_date"] if sessions else None
    eligible_setups = [{
        "id": t["id"], "symbol": t["symbol"], "signal_date": t["signal_date"],
        "reference_close": t["reference_close"], "stop_loss": t["stop_loss"],
        "target_price": t["target_price"], "planned_quantity": t["planned_quantity"],
        "confidence_pct": t["confidence_pct"], "relative_strength": t["signal_rank"],
        "status": t["status"],
    } for t in trades if t["signal_date"] == latest_session
       and t["status"] in {"PENDING_APPROVAL", "QUEUED"}]
    return {"summary": summary, "trades": trades, "sessions": sessions,
            "latest_session": latest_session, "eligible_setups": eligible_setups}
