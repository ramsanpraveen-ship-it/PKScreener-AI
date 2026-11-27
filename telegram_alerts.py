"""Opt-in Telegram notifications. No network call occurs unless requested."""

import requests


def telegram_configured(token, chat_id):
    return bool(token and chat_id)


def format_candidate_alert(scan):
    if scan.get("status") != "FRESH":
        raise ValueError("Telegram alerts require a fresh validated scan")
    expected = scan.get("expected_session")
    if not expected or not scan.get("candidates"):
        raise ValueError("No fresh candidates are available to alert")
    lines = [f"PKScreener research candidates · NSE {expected}"]
    for row in scan["candidates"][:30]:
        symbol = str(row.get("symbol", "")).strip().upper()
        status = str(row.get("candidate_status", "")).strip()
        if symbol and status in {"BREAKOUT_CONFIRMED", "SETUP_WATCH"}:
            lines.append(f"{symbol} — {status}")
    if len(lines) == 1:
        raise ValueError("No qualifying candidates are available to alert")
    return "\n".join(lines)


def send_telegram_alert(scan, token, chat_id, post=requests.post):
    if not telegram_configured(token, chat_id):
        raise ValueError("Telegram bot token and chat ID are not configured")
    message = format_candidate_alert(scan)
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        response = post(
            url,
            json={"chat_id": chat_id, "text": message, "disable_web_page_preview": True},
            timeout=10,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("ok") is not True:
            raise ValueError("Telegram rejected the alert")
    except Exception as error:
        # Never return or log the URL because it contains the bot token.
        raise RuntimeError("Telegram alert delivery failed") from error
    return {"sent": True, "candidate_count": len(message.splitlines()) - 1}
