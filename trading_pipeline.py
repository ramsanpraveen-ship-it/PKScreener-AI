
import json

from technical_engine import run_technical_analysis
from risk_manager import calculate_position_size
from ai_analyst import analyse_candidate


# ==========================================
# ACCOUNT CONFIGURATION
# ==========================================

ACCOUNT = {
    "total_capital": 100_000,
    "deployed_capital": 0,
    "open_positions_count": 0,
    "aggregate_open_risk": 0,
}

DEFAULT_SYMBOL = "RELIANCE"
DEFAULT_PERIOD = "2y"


def build_ai_candidate(technical_result, risk_result):
    """Provide only Python-calculated facts and risk outputs to the local LLM."""
    trend = technical_result.get("trend_analysis", {})
    contraction = technical_result.get("contraction_analysis", {})
    breakout = technical_result.get("breakout_analysis", {})
    entry_exit = technical_result.get("entry_exit_analysis", {})
    trend_averages = trend.get("moving_averages", {})
    volume = breakout.get("volume_analysis", {})
    contractions = contraction.get("contractions", [])
    last_contraction = contractions[-1] if contractions else {}
    approved = risk_result.get("approved_for_sizing") is True
    return {
        "symbol": technical_result.get("symbol"),
        "analysis_date": technical_result.get("analysis_date"),
        "candidate_status": technical_result.get("screening_summary", {}).get("candidate_status"),
        "price": technical_result.get("latest_price"),
        "completed_daily_close": technical_result.get("latest_price"),
        "trend_conditions_passed": trend.get("conditions_passed"),
        "trend_conditions": trend.get("conditions"),
        "moving_averages": trend_averages,
        "contractions": [item.get("depth_pct") for item in contractions],
        "contraction_low": entry_exit.get("structural_swing_low", last_contraction.get("low")),
        "volume_ratio": volume.get("volume_ratio"),
        "volume_baseline": volume.get("average_volume"),
        "volume_confirmed": volume.get("volume_confirmed"),
        "pivot": (breakout.get("pivot") or {}).get("pivot_price"),
        "breakout_status": breakout.get("status"),
        "breakout_confirmed": breakout.get("breakout_confirmed"),
        "python_results": {
            "entry_price": entry_exit.get("entry_price"),
            "stop_loss": entry_exit.get("stop_loss"),
            "target_reference_2r": entry_exit.get("target_reference_2r"),
            "approved_for_sizing": approved,
            "quantity": risk_result.get("quantity") if approved else None,
            "maximum_trade_risk": risk_result.get("maximum_trade_risk") if approved else None,
            "risk_budget": risk_result.get("risk_budget", 500),
            "investment_value": risk_result.get("investment_value") if approved else None,
        },
    }


# ==========================================
# TRADING PIPELINE
# ==========================================

def run_pipeline(
    symbol=DEFAULT_SYMBOL,
    period=DEFAULT_PERIOD,
    account=None
):

    symbol = symbol.upper().strip()

    account_state = (
        dict(account)
        if account is not None
        else dict(ACCOUNT)
    )

    print("\n" + "=" * 50)
    print("       NSE SWING TRADING PIPELINE")
    print("=" * 50)

    print(f"\nSymbol: {symbol}")
    print(f"Historical period: {period}")

    # --------------------------------------
    # STEP 1: TECHNICAL ANALYSIS
    # --------------------------------------

    print("\n[1/3] Running technical analysis...")

    technical_result = run_technical_analysis(
        symbol=symbol,
        period=period
    )

    screening = technical_result.get(
        "screening_summary", {}
    )

    candidate_status = screening.get(
        "candidate_status",
        "NOT_QUALIFIED"
    )

    print("\nTechnical Analysis Summary")
    print("-" * 40)

    print(f"Symbol: {symbol}")

    print(
        "Trend Template:",
        screening.get("trend_template_pass")
    )

    print(
        "Relative Strength:",
        screening.get("relative_strength_pass")
    )

    print(
        "VCP Sequence:",
        screening.get("vcp_sequence_pass")
    )

    print(
        "Breakout Confirmed:",
        screening.get("breakout_confirmed")
    )

    print(
        "Candidate Status:",
        candidate_status
    )

    # --------------------------------------
    # STEP 2: PREPARE CANDIDATE
    # --------------------------------------

    print("\n[2/3] Preparing candidate for risk manager...")

    entry_exit = technical_result.get(
        "entry_exit_analysis", {}
    )

    entry_exit_approved = (
        entry_exit.get("approved_for_entry") is True
    )

    # Only pass prices when both technical
    # qualification and entry/exit validation pass.

    can_submit_for_sizing = (
        candidate_status == "BREAKOUT_CONFIRMED"
        and entry_exit_approved
    )

    candidate = {

        "symbol": symbol,

        "candidate_status": candidate_status,

        "entry_price": (
            entry_exit.get("entry_price")
            if can_submit_for_sizing
            else None
        ),

        "stop_loss": (
            entry_exit.get("stop_loss")
            if can_submit_for_sizing
            else None
        )
    }

    print("\nEntry/Exit Analysis:")

    print(
        json.dumps(
            entry_exit,
            indent=4,
            default=str
        )
    )

    if can_submit_for_sizing:

        print("\nEntry:", candidate["entry_price"])
        print("Stop Loss:", candidate["stop_loss"])

        print(
            "2R Reference:",
            entry_exit.get("target_reference_2r")
        )

    else:

        print(
            "\nEntry/Exit not eligible for position sizing."
        )

        if candidate_status != "BREAKOUT_CONFIRMED":

            print(
                "Reason: Technical screening qualification failed."
            )

        elif not entry_exit_approved:

            print(
                "Reason: Entry/exit validation failed."
            )

    # --------------------------------------
    # STEP 3: RISK MANAGEMENT
    # --------------------------------------

    print("\n[3/3] Running risk validation...")

    risk_result = calculate_position_size(
        candidate,
        account_state
    )

    # Local AI explains shortlisted candidates only. Python remains the sole
    # source of numerical entry, stop, target, and position-size values.
    ai_result = None
    if candidate_status in ("BREAKOUT_CONFIRMED", "SETUP_WATCH"):
        try:
            ai_result = analyse_candidate(build_ai_candidate(technical_result, risk_result))
        except Exception as error:
            ai_result = {
                "status": "UNAVAILABLE",
                "reason": str(error),
                "manual_approval_required": True,
                "order_placed": False,
            }

    # --------------------------------------
    # FINAL DECISION
    # --------------------------------------

    print("\n" + "=" * 50)
    print("              FINAL DECISION")
    print("=" * 50)

    print("\nTechnical Status:")
    print(candidate_status)

    print("\nRisk Manager Result:")

    print(
        json.dumps(
            risk_result,
            indent=4,
            default=str
        )
    )

    if ai_result is not None:
        print("\nLocal AI explanation:")
        print(json.dumps(ai_result, indent=4, default=str))

    print("\n" + "=" * 50)

    if risk_result.get("approved_for_sizing"):

        print("CANDIDATE APPROVED FOR POSITION SIZING")

        print(
            "Quantity:",
            risk_result["quantity"]
        )

        print(
            "Investment:",
            risk_result["investment_value"]
        )

        print(
            "Maximum Planned Risk:",
            risk_result["maximum_trade_risk"]
        )

        print("\nManual approval is still required.")
        print("No order has been placed.")

    else:

        print("CANDIDATE REJECTED")
        print("No trade will be initiated.")

    print("=" * 50)

    return {
        "symbol": symbol,
        "technical_result": technical_result,
        "candidate": candidate,
        "risk_result": risk_result,
        "ai_analysis": ai_result,
    }


# ==========================================
# MAIN
# ==========================================

if __name__ == "__main__":

    run_pipeline(
        symbol=DEFAULT_SYMBOL,
        period=DEFAULT_PERIOD
    )
