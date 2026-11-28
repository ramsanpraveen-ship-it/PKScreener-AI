from contextlib import asynccontextmanager
import csv
from datetime import datetime
import json
from pathlib import Path
import re
import os
import secrets

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from nse_calendar import get_latest_expected_nse_session
from risk_manager import (
    TOTAL_CAPITAL,
    MAX_DEPLOYMENT,
    MAX_RISK_PER_TRADE,
    MAX_OPEN_POSITIONS,
    MAX_POSITION_VALUE,
    MAX_AGGREGATE_OPEN_RISK,
)
from .db import SessionLocal, get_db, initialize_database
from .models import PaperTrade, PortfolioPosition, WatchlistItem
from .scan_service import load_latest_scan
from .schemas import (
    ManualCloseRequest, ManualPositionRequest, PaperTradeCloseRequest,
    PaperTradeRequest, TelegramAlertRequest, WatchlistRequest,
)
from paper_trading import summarize_paper_trades, validate_paper_entry
from telegram_alerts import send_telegram_alert, telegram_configured
from forward_paper import get_forward_book, get_mode, set_mode, approve_signal


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SYMBOL_PATTERN = re.compile(r"^[A-Z0-9&._-]{1,32}$")


@asynccontextmanager
async def lifespan(app):
    try:
        initialize_database()
        app.state.database_initialized = True
    except Exception:
        # Keep read-only scanner status available while the local database is configured.
        app.state.database_initialized = False
    yield


app = FastAPI(
    title="PKScreener-AI Local API",
    version="1.0.0",
    description="Local NSE cash-equity research API. It does not submit orders.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type", "Authorization"],
)


@app.middleware("http")
async def require_local_api_token(request, call_next):
    if not request.url.path.startswith("/api/"):
        return await call_next(request)
    client_host = request.client.host if request.client else ""
    if client_host not in {"127.0.0.1", "::1", "localhost"}:
        return JSONResponse({"detail": "Local API access only"}, status_code=403)
    if request.url.path == "/api/health":
        return await call_next(request)
    configured = os.environ.get("PKSCREENER_API_TOKEN", "")
    supplied = request.headers.get("Authorization", "")
    expected = f"Bearer {configured}" if configured else ""
    if not configured:
        return JSONResponse({"detail": "Local API token is not configured"}, status_code=503)
    if not secrets.compare_digest(supplied, expected):
        return JSONResponse({"detail": "Authentication required"}, status_code=401)
    return await call_next(request)


def _expected_session():
    return str(get_latest_expected_nse_session())


def _scan():
    return load_latest_scan(PROJECT_ROOT, _expected_session())


def _clean_symbol(value):
    symbol = (value or "").strip().upper()
    if not SYMBOL_PATTERN.fullmatch(symbol):
        raise HTTPException(status_code=422, detail="Enter a valid NSE cash-equity symbol")
    return symbol


def _position_payload(position, scan):
    mark = None
    if scan["status"] == "FRESH":
        for row in scan["candidates"]:
            if row.get("symbol", "").strip().upper() == position.symbol:
                try:
                    mark = float(row["latest_price"])
                except (TypeError, ValueError):
                    mark = None
                break
    unrealized = ((mark - position.entry_price) * position.quantity
                  if mark is not None and position.status == "OPEN" else None)
    return {
        "id": position.id,
        "symbol": position.symbol,
        "quantity": position.quantity,
        "entry_price": position.entry_price,
        "stop_loss": position.stop_loss,
        "target_price": position.target_price,
        "opened_on": position.opened_on.isoformat(),
        "status": position.status,
        "mark_price": mark,
        "unrealized_pnl": unrealized,
        "exit_price": position.exit_price,
        "closed_on": position.closed_on.isoformat() if position.closed_on else None,
        "manual_record_only": True,
    }


@app.get("/api/health")
def health():
    database_available = False
    try:
        with SessionLocal() as session:
            session.execute(select(1))
        database_available = True
    except SQLAlchemyError:
        pass
    return {
        "status": "ok",
        "database_available": database_available,
        "scan_status": _scan()["status"],
        "local_only": True,
        "orders_enabled": False,
        "telegram_configured": telegram_configured(
            os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
        ),
    }


@app.get("/api/backtest")
def historical_backtest():
    """Read the latest local historical paper replay output bundle."""
    results = PROJECT_ROOT / "data" / "backtest" / "results"
    metrics_path = results / "backtest_metrics.json"
    assumptions_path = results / "backtest_assumptions.json"
    trades_path = results / "backtest_trades.csv"
    curve_path = results / "backtest_equity_curve.csv"
    if not all(path.is_file() for path in (metrics_path, assumptions_path, trades_path)):
        return {"available": False, "metrics": None, "assumptions": {}, "trades": [], "equity_curve": []}
    try:
        metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
        assumptions = json.loads(assumptions_path.read_text(encoding="utf-8"))
        with trades_path.open(newline="", encoding="utf-8") as stream:
            trades = list(csv.DictReader(stream))
        equity_curve = []
        if curve_path.is_file():
            with curve_path.open(newline="", encoding="utf-8") as stream:
                equity_curve = list(csv.DictReader(stream))
    except (OSError, json.JSONDecodeError, csv.Error) as error:
        raise HTTPException(status_code=503, detail=f"Historical replay output is incomplete: {error}")
    return {
        "available": True,
        "metrics": metrics,
        "assumptions": assumptions,
        "trades": trades,
        "equity_curve": equity_curve,
        "live_orders_placed": False,
    }


@app.get("/api/strategy-intelligence")
def strategy_intelligence():
    """Read the newest non-gating baseline feature/failure diagnostic artifact."""
    experiment_root = PROJECT_ROOT / "data" / "backtest" / "experiments"
    reports = sorted(experiment_root.glob("strategy_intelligence_*/diagnostics.json"))
    if not reports:
        return {"available": False, "live_orders_enabled": False}
    path = reports[-1]
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise HTTPException(status_code=503, detail=f"Strategy diagnostic is unavailable: {error}")
    trades = [{
        "symbol": item["symbol"],
        "signal_date": item["signal_date"],
        "net_pnl": item["net_pnl"],
        "exit_reason": item["exit_reason"],
        "market_regime": item["market_regime"]["classification"],
        "rs_percentile": item["relative_strength"]["internal_cross_sectional_relative_percentile"],
        "contraction_depths_pct": item["vcp_features"]["contraction_depths_pct_oldest_to_newest"],
        "higher_lows": item["vcp_features"]["higher_lows"],
        "contraction_volume_ratio": item["vcp_features"]["average_contraction_volume_ratio"],
        "breakout_relative_volume": item["breakout_features"]["relative_volume_20d"],
        "breakout_close_position": item["breakout_features"]["breakout_close_position"],
        "mfe_r": item["excursion"]["mfe_r"],
        "mae_r": item["excursion"]["mae_r"],
        "first_threshold": item["excursion"]["first_threshold"],
        "loss_tags": item["descriptive_loss_tags"],
        "censored_at_test_end": item["censored_at_test_end"],
    } for item in report.get("trades", [])]
    return {
        "available": True,
        "baseline_id": report.get("baseline_id"),
        "generated_at": report.get("generated_at"),
        "performance_window": report.get("performance_window"),
        "trade_count": report.get("trade_count"),
        "baseline_metrics": report.get("baseline_metrics"),
        "diagnostic_summary": report.get("diagnostic_summary"),
        "loss_tag_counts": report.get("loss_tag_counts", {}),
        "feature_semantics": report.get("feature_semantics", {}),
        "experiment_status": report.get("experiment_status"),
        "limitations": report.get("limitations", []),
        "trades": trades,
        "live_orders_enabled": False,
    }


@app.get("/api/dashboard")
def dashboard():
    scan = _scan()
    watchlist = []
    positions = []
    database_available = False
    try:
        with SessionLocal() as session:
            session.execute(select(1))
            database_available = True
            watchlist = [
                {"symbol": item.symbol, "added_at": item.added_at.isoformat()}
                for item in session.scalars(select(WatchlistItem).order_by(WatchlistItem.symbol)).all()
            ]
            positions = [
                _position_payload(item, scan)
                for item in session.scalars(
                    select(PortfolioPosition).order_by(PortfolioPosition.opened_on.desc())
                ).all()
            ]
    except SQLAlchemyError:
        database_available = False

    return {
        "as_of": datetime.now().astimezone().isoformat(),
        "freshness": scan,
        "risk_config": {
            "total_capital": TOTAL_CAPITAL,
            "max_deployment": MAX_DEPLOYMENT,
            "max_risk_per_trade": MAX_RISK_PER_TRADE,
            "max_open_positions": MAX_OPEN_POSITIONS,
            "max_position_value": MAX_POSITION_VALUE,
        "max_aggregate_open_risk": MAX_AGGREGATE_OPEN_RISK,
            "holding_sessions": [2, 20],
        },
        "watchlist": watchlist,
        "portfolio": positions,
        "database_available": database_available,
        "local_only": True,
        "orders_enabled": False,
        "telegram_configured": telegram_configured(
            os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
        ),
    }


@app.get("/api/watchlist")
def get_watchlist(db: Session = Depends(get_db)):
    return [
        {"symbol": item.symbol, "added_at": item.added_at.isoformat()}
        for item in db.scalars(select(WatchlistItem).order_by(WatchlistItem.symbol)).all()
    ]


@app.post("/api/watchlist", status_code=201)
def add_watchlist_item(body: WatchlistRequest, db: Session = Depends(get_db)):
    symbol = _clean_symbol(body.symbol)
    existing = db.scalar(select(WatchlistItem).where(WatchlistItem.symbol == symbol))
    if existing:
        return {"symbol": existing.symbol, "created": False}
    item = WatchlistItem(symbol=symbol)
    db.add(item)
    db.commit()
    return {"symbol": symbol, "created": True}


@app.delete("/api/watchlist/{symbol}", status_code=204)
def delete_watchlist_item(symbol: str, db: Session = Depends(get_db)):
    symbol = _clean_symbol(symbol)
    item = db.scalar(select(WatchlistItem).where(WatchlistItem.symbol == symbol))
    if item:
        db.delete(item)
        db.commit()
    return None


@app.get("/api/portfolio")
def get_portfolio(db: Session = Depends(get_db)):
    scan = _scan()
    items = db.scalars(select(PortfolioPosition).order_by(PortfolioPosition.opened_on.desc())).all()
    return [_position_payload(item, scan) for item in items]


@app.post("/api/portfolio", status_code=201)
def add_manual_position(body: ManualPositionRequest, db: Session = Depends(get_db)):
    db.execute(text("SELECT pg_advisory_xact_lock(505051)"))
    if body.manual_recorded is not True:
        raise HTTPException(status_code=422, detail="Confirm this is a manually recorded existing position")
    symbol = _clean_symbol(body.symbol)
    if body.stop_loss >= body.entry_price:
        raise HTTPException(status_code=422, detail="Stop loss must be below entry price for a long cash position")
    if body.target_price is not None and body.target_price <= body.entry_price:
        raise HTTPException(status_code=422, detail="Target reference must be above entry price")
    planned_risk = (body.entry_price - body.stop_loss) * body.quantity
    investment = body.entry_price * body.quantity
    if planned_risk > MAX_RISK_PER_TRADE:
        raise HTTPException(status_code=422, detail="Recorded position exceeds the ₹500 planned risk limit")
    if investment > MAX_POSITION_VALUE:
        raise HTTPException(status_code=422, detail="Recorded position exceeds the ₹20,000 per-position limit")
    open_items = db.scalars(select(PortfolioPosition).where(PortfolioPosition.status == "OPEN")).all()
    aggregate_risk = sum((item.entry_price - item.stop_loss) * item.quantity for item in open_items)
    if aggregate_risk + planned_risk > MAX_AGGREGATE_OPEN_RISK:
        raise HTTPException(status_code=422, detail="Recorded positions would exceed the ₹1,500 aggregate risk limit")
    if len(open_items) >= MAX_OPEN_POSITIONS:
        raise HTTPException(status_code=422, detail="Maximum three open positions reached")
    deployed = sum(item.entry_price * item.quantity for item in open_items)
    if deployed + investment > MAX_DEPLOYMENT or deployed + investment > TOTAL_CAPITAL:
        raise HTTPException(status_code=422, detail="Recorded positions would exceed deployment limits")
    position = PortfolioPosition(
        symbol=symbol,
        quantity=body.quantity,
        entry_price=body.entry_price,
        stop_loss=body.stop_loss,
        target_price=body.target_price,
        opened_on=body.opened_on,
        status="OPEN",
    )
    db.add(position)
    db.commit()
    db.refresh(position)
    return {"id": position.id, "symbol": symbol, "manual_record_only": True, "order_placed": False}


@app.post("/api/portfolio/{position_id}/close")
def close_manual_position(position_id: int, body: ManualCloseRequest, db: Session = Depends(get_db)):
    if body.manual_confirmation is not True:
        raise HTTPException(status_code=422, detail="Confirm that this position was closed manually")
    position = db.get(PortfolioPosition, position_id)
    if position is None:
        raise HTTPException(status_code=404, detail="Position not found")
    if position.status != "OPEN":
        raise HTTPException(status_code=409, detail="Position is already closed")
    position.status = "CLOSED"
    position.exit_price = body.exit_price
    position.closed_on = body.closed_on
    db.commit()
    return {"id": position.id, "symbol": position.symbol, "status": "CLOSED", "order_placed": False}


@app.get("/api/forward-paper")
def get_forward_paper():
    book = get_forward_book()
    book["summary"]["mode"] = get_mode()
    return book


@app.put("/api/forward-paper/mode")
def update_forward_paper_mode(body: dict):
    try:
        mode = set_mode(str(body.get("mode", "")))
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return {"mode": mode, "live_orders_enabled": False}


@app.post("/api/forward-paper/{trade_id}/approve")
def approve_forward_paper_trade(trade_id: int, body: dict):
    if body.get("manual_confirmation") is not True:
        raise HTTPException(status_code=422, detail="Confirm this simulated trade for next-session paper entry")
    if not approve_signal(trade_id):
        raise HTTPException(status_code=409, detail="Trade is no longer awaiting approval")
    return {"id": trade_id, "status": "QUEUED", "simulated_only": True, "order_placed": False}


@app.get("/api/paper-trades")
def get_paper_trades(db: Session = Depends(get_db)):
    trades = db.scalars(select(PaperTrade).order_by(PaperTrade.opened_on.desc())).all()
    rows = [{
        "id": item.id, "symbol": item.symbol, "quantity": item.quantity,
        "entry_price": item.entry_price, "stop_loss": item.stop_loss,
        "target_price": item.target_price, "opened_on": item.opened_on.isoformat(),
        "status": item.status, "exit_price": item.exit_price,
        "closed_on": item.closed_on.isoformat() if item.closed_on else None,
        "realized_pnl_before_costs": ((item.exit_price - item.entry_price) * item.quantity
                                       if item.status == "CLOSED" else None),
    } for item in trades]
    return {"summary": summarize_paper_trades(rows), "trades": rows}


@app.post("/api/paper-trades", status_code=201)
def add_paper_trade(body: PaperTradeRequest, db: Session = Depends(get_db)):
    db.execute(text("SELECT pg_advisory_xact_lock(505051)"))
    if body.simulation_confirmation is not True:
        raise HTTPException(status_code=422, detail="Confirm this is a simulated paper trade")
    symbol = _clean_symbol(body.symbol)
    if body.target_price is not None and body.target_price <= body.entry_price:
        raise HTTPException(status_code=422, detail="Target reference must be above entry price")
    open_items = db.scalars(select(PaperTrade).where(PaperTrade.status == "OPEN")).all()
    deployed = sum(item.entry_price * item.quantity for item in open_items)
    aggregate_risk = sum((item.entry_price - item.stop_loss) * item.quantity for item in open_items)
    try:
        validate_paper_entry(body.entry_price, body.stop_loss, body.quantity, len(open_items), deployed, aggregate_risk)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    trade = PaperTrade(
        symbol=symbol, quantity=body.quantity, entry_price=body.entry_price,
        stop_loss=body.stop_loss, target_price=body.target_price,
        opened_on=body.opened_on, status="OPEN",
    )
    db.add(trade)
    db.commit()
    db.refresh(trade)
    return {"id": trade.id, "symbol": symbol, "status": "OPEN", "simulated_only": True, "order_placed": False}


@app.post("/api/paper-trades/{trade_id}/close")
def close_paper_trade(trade_id: int, body: PaperTradeCloseRequest, db: Session = Depends(get_db)):
    if body.simulation_confirmation is not True:
        raise HTTPException(status_code=422, detail="Confirm this is a simulated close")
    trade = db.get(PaperTrade, trade_id)
    if trade is None:
        raise HTTPException(status_code=404, detail="Paper trade not found")
    if trade.status != "OPEN":
        raise HTTPException(status_code=409, detail="Paper trade is already closed")
    trade.status = "CLOSED"
    trade.exit_price = body.exit_price
    trade.closed_on = body.closed_on
    db.commit()
    return {"id": trade.id, "symbol": trade.symbol, "status": "CLOSED", "simulated_only": True, "order_placed": False}


@app.post("/api/alerts/telegram")
def send_manual_telegram_alert(body: TelegramAlertRequest):
    if body.manual_confirmation is not True:
        raise HTTPException(status_code=422, detail="Confirm that you want to send a Telegram alert")
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not telegram_configured(token, chat_id):
        raise HTTPException(status_code=503, detail="Telegram alerts are not configured")
    try:
        result = send_telegram_alert(_scan(), token, chat_id)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    return {**result, "external_service": "Telegram", "order_placed": False}
