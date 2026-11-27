
import json
import requests
from risk_manager import MAX_RISK_PER_TRADE

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "nse-analyst"

SYSTEM_PROMPT = """
You are an NSE cash-equity VCP research analyst.

Follow these rules:
- Use only supplied market data.
- Never invent missing values.
- Price above moving averages alone does not prove a complete trend.
- Do not assume moving averages are rising without historical data.
- Decreasing contractions are positive but do not prove a VCP.
- A breakout requires a completed daily close above the supplied pivot.
- Volume confirmation requires a defined volume baseline.
- Never assume a universal 2x volume requirement.
- Missing contraction low means stop_loss must be null.
- Missing completed daily close means breakout is UNCONFIRMED.
- Missing volume baseline means volume_confirmation is UNKNOWN.
- Never invent entry, stop, target or quantity.
- Never recommend F&O, leverage or automated orders.
- Treat supplied Python calculation fields as authoritative; mirror them verbatim.
- Do not add numerical claims not present in the supplied Python fields.
- Keep all assessment text explicitly explanatory, not a trading instruction.

Return valid JSON only, with these exact top-level fields:
symbol,
trend_alignment,
vcp_quality,
breakout_confirmation,
entry_price,
stop_loss,
target,
position_sizing,
missing_information,
risk_notes,
assessment.

Use null for unavailable numerical values.
"""

REQUIRED_FIELDS = [
    "symbol",
    "trend_alignment",
    "vcp_quality",
    "breakout_confirmation",
    "entry_price",
    "stop_loss",
    "target",
    "position_sizing",
    "missing_information",
    "risk_notes",
    "assessment"
]



def _python_authority(candidate):
    supplied = candidate.get("python_results")
    return supplied if isinstance(supplied, dict) else candidate


def validate_and_guard(result, candidate):
    """Keep every numeric decision field under Python's control."""
    if not isinstance(result, dict):
        raise ValueError("AI response is not a JSON object")
    missing = [key for key in REQUIRED_FIELDS if key not in result]
    if missing:
        raise ValueError(f"Missing fields: {missing}")

    breakout = result["breakout_confirmation"]
    if isinstance(breakout, str):
        breakout = {"status": breakout, "reason": "Normalized from AI response",
                    "volume_confirmation": "UNKNOWN"}
    elif isinstance(breakout, dict):
        breakout = dict(breakout)
        breakout.setdefault("status", "UNCONFIRMED")
        breakout.setdefault("reason", "Not supplied")
        breakout.setdefault("volume_confirmation", "UNKNOWN")
    else:
        breakout = {"status": "UNCONFIRMED", "reason": "Model response was not structured",
                    "volume_confirmation": "UNKNOWN"}

    authority = _python_authority(candidate)
    entry_price = authority.get("entry_price")
    stop_loss = authority.get("stop_loss")
    target = authority.get("target_reference_2r", authority.get("target"))
    if candidate.get("completed_daily_close") is None:
        entry_price = stop_loss = target = None
        breakout["status"] = "UNCONFIRMED"
    elif candidate.get("breakout_confirmed") is not True:
        breakout["status"] = candidate.get("breakout_status") or "UNCONFIRMED"
    elif candidate.get("breakout_status") is not None:
        breakout["status"] = candidate["breakout_status"]
    if candidate.get("breakout_confirmed") is not None:
        breakout["confirmed"] = bool(candidate["breakout_confirmed"])
    if candidate.get("volume_baseline") is None or candidate.get("volume_confirmed") is None:
        breakout["volume_confirmation"] = "UNKNOWN"
    else:
        breakout["volume_confirmation"] = (
            "CONFIRMED" if candidate["volume_confirmed"] is True else "NOT_CONFIRMED"
        )
    if candidate.get("contraction_low") is None:
        stop_loss = None

    approved = authority.get("approved_for_sizing") is True
    quantity = authority.get("quantity") if approved else None
    risk_per_trade = authority.get("maximum_trade_risk") if approved else None
    if entry_price is None or stop_loss is None:
        quantity = risk_per_trade = None

    guarded = {key: result[key] for key in REQUIRED_FIELDS}
    guarded["symbol"] = candidate.get("symbol")
    guarded["breakout_confirmation"] = breakout
    guarded["entry_price"] = entry_price
    guarded["stop_loss"] = stop_loss
    guarded["target"] = target if entry_price is not None and stop_loss is not None else None
    guarded["position_sizing"] = {
        "quantity": quantity,
        "risk_per_trade": risk_per_trade,
        "risk_budget": authority.get("risk_budget", MAX_RISK_PER_TRADE),
        "investment_value": authority.get("investment_value") if approved else None,
        "manual_approval_required": True,
        "order_placed": False,
    }
    notes = guarded.get("risk_notes")
    if isinstance(notes, list):
        guarded["risk_notes"] = notes + [
            "Numerical levels and sizing are controlled by the Python engine.",
            "This local AI output is explanatory only; manual approval is required.",
        ]
    return guarded


def analyse_candidate(candidate):

    prompt = f"""
Analyse this NSE cash-equity candidate.

MARKET DATA:
{json.dumps(candidate, indent=2)}

Evaluate:
1. Trend alignment
2. VCP structure and contraction quality
3. Breakout confirmation
4. Volume confirmation
5. Missing information
6. Risk factors

Return the exact JSON structure specified in your system
instructions.

Do not calculate or invent missing trading values.
"""

    payload = {
        "model": MODEL,
        "stream": False,
        "format": "json",
        "options": {
            "temperature": 0.1
        },
        "messages": [
            {
                "role": "system",
                "content": SYSTEM_PROMPT
            },
            {
                "role": "user",
                "content": prompt
            }
        ]
    }

    response = requests.post(
        OLLAMA_URL,
        json=payload,
        timeout=180
    )

    response.raise_for_status()

    response_data = response.json()
    content = response_data["message"]["content"]

    result = json.loads(content)

    return validate_and_guard(result, candidate)


if __name__ == "__main__":

    sample = {
        "symbol": "EXAMPLE",
        "price": 502,

        "dma20": 490,
        "dma50": 480,
        "dma200": 430,

        "dma50_previous": None,
        "dma200_previous": None,

        "pivot": 500,
        "completed_daily_close": None,

        "volume_ratio": 1.7,
        "volume_baseline": None,

        "contractions": [18, 12, 7, 3],
        "contraction_low": None,
        "atr": None,

        "average_traded_value_20d": None
    }

    try:
        analysis = analyse_candidate(sample)

        print("\n===== NSE AI ANALYSIS =====\n")
        print(json.dumps(analysis, indent=2))

    except Exception as error:
        print("Analysis failed:", str(error))
