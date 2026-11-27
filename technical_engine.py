
import json
import traceback
import time

from market_data import fetch_stock_data

from swing_detector import analyse_swings

from contraction_analyzer import analyse_contractions

from trend_analyzer import analyse_trend_template

from relative_strength import (
    fetch_close_prices,
    analyse_relative_strength_from_data,
    INDEX_SYMBOL
)

from breakout_analyzer import analyse_breakout

from entry_exit_analyzer import analyse_entry_exit

from nse_calendar import validate_market_data_freshness


# ==========================================
# CONFIGURATION
# ==========================================

DEFAULT_SYMBOL = "RELIANCE"
PERIOD = "2y"


# ==========================================
# TECHNICAL ENGINE
# ==========================================

def run_technical_analysis(
    symbol=DEFAULT_SYMBOL,
    period=PERIOD,
    benchmark_df=None
):

    print("\n======================================")
    print(f"TECHNICAL ANALYSIS ENGINE: {symbol}")
    print("======================================\n")

    # --------------------------------------
    # 1. FETCH STOCK DATA ONCE
    # --------------------------------------

    print("[1/6] Fetching stock market data...")

    stock_df = None

    if benchmark_df is None:
        benchmark_df = fetch_close_prices(
            INDEX_SYMBOL,
            period=period
        )

    last_error = None
    for attempt in range(3):
        stock_df = fetch_stock_data(symbol, period=period)
        try:
            freshness_result = validate_market_data_freshness(stock_df, benchmark_df)
            break
        except ValueError as error:
            last_error = error
            if attempt == 2:
                raise RuntimeError(f"DATA_DOWNLOAD_FAILED after 3 stock attempts for {symbol}: {error}") from error
            time.sleep(1.0 * (2 ** attempt))

    print(
        "Market data freshness:",
        freshness_result
    )
    print(
        f"      Loaded {len(stock_df)} candles"
    )

    aligned_sessions = len(
        stock_df["Close"].dropna().index.intersection(benchmark_df.dropna().index)
    )
    if aligned_sessions < 253:
        latest_date = str(stock_df.index[-1].date())
        latest_source = (
            str(stock_df["DataSource"].iloc[-1])
            if "DataSource" in stock_df.columns
            else "Yahoo Finance auto-adjusted OHLCV"
        )
        print(
            f"      Skipping: {aligned_sessions}/253 aligned sessions; "
            "insufficient history for the existing rules"
        )
        return {
            "symbol": symbol,
            "analysis_date": latest_date,
            "latest_price": round(float(stock_df["Close"].iloc[-1]), 2),
            "data_info": {
                "stock_ticker": f"{symbol}.NS",
                "benchmark": "NIFTY 50",
                "stock_candles": int(len(stock_df)),
                "aligned_sessions": aligned_sessions,
                "period": period,
                "latest_bar_source": latest_source,
            },
            "trend_analysis": {"conditions_passed": 0},
            "relative_strength_analysis": {"weighted_relative_performance": None},
            "contraction_analysis": {},
            "breakout_analysis": {
                "status": "INSUFFICIENT_HISTORY",
                "breakout_confirmed": False,
            },
            "entry_exit_analysis": {},
            "screening_summary": {
                "trend_template_pass": False,
                "relative_strength_pass": False,
                "vcp_sequence_pass": False,
                "breakout_confirmed": False,
                "core_conditions_pass": False,
                "candidate_status": "INSUFFICIENT_HISTORY",
            },
        }

    # --------------------------------------
    # 2. SWING DETECTION
    # --------------------------------------

    print("\n[2/6] Running swing detection...")

    swing_result = analyse_swings(
        stock_df
    )

    print(
        f"      Raw swings: {swing_result['raw_swing_count']}"
    )

    print(
        "      Normalized swings:",
        swing_result["normalized_swing_count"]
    )

    # --------------------------------------
    # 3. VCP CONTRACTION ANALYSIS
    # --------------------------------------

    print("\n[3/6] Running VCP contraction analysis...")

    contraction_result = analyse_contractions(
        stock_df,
        symbol=symbol
    )

    print(
        "      Contractions:",
        contraction_result["contraction_count"]
    )

    # --------------------------------------
    # 4. TREND TEMPLATE
    # --------------------------------------

    print("\n[4/6] Running Minervini trend analysis...")

    trend_result = analyse_trend_template(
        stock_df,
        symbol=symbol
    )

    print(
        "      Conditions passed:",
        trend_result["conditions_passed"],
        "/",
        trend_result["total_conditions"]
    )

    # --------------------------------------
    # 5. RELATIVE STRENGTH
    # --------------------------------------

    
    print("\n[5/6] Running relative strength analysis...")

    print("      Using validated Nifty 50 benchmark data...")

    relative_strength_result = (
        analyse_relative_strength_from_data(
            stock_df["Close"],
            benchmark_df,
            symbol=symbol
        )
    )

    print(
        "      Weighted relative performance:",
        relative_strength_result[
            "weighted_relative_performance"
        ],
        "%"
    )

    # --------------------------------------
    # 6. BREAKOUT ANALYSIS
    # --------------------------------------

    print("\n[6/6] Running breakout analysis...")

    breakout_result = analyse_breakout(
        stock_df,
        symbol=symbol
    )
    print("\n[7/7] Running entry and exit analysis...")

    entry_exit_result = analyse_entry_exit(
        df=stock_df,
        swing_analysis=swing_result,
        breakout_analysis=breakout_result,
        symbol=symbol
    )

    print(
        "      Entry/exit status:",
        entry_exit_result["status"]
    )

    print(
        "      Breakout status:",
        breakout_result["status"]
    )

    # ======================================
    # COMBINE RESULTS
    # ======================================

    latest_price = float(
        stock_df["Close"].iloc[-1]
    )

    latest_date = str(
        stock_df.index[-1].date()
    )

    # Trend qualification.
    trend_pass = bool(
        trend_result["trend_template_pass_without_rs"]
    )

    # Relative strength qualification.
    # Relative strength qualification.
    relative_strength_pass = bool(
        relative_strength_result["relative_strength_pass"]
    )

    # VCP contraction qualification.
    contraction_sequence = (
        contraction_result["contraction_sequence"]
    )

    vcp_sequence_pass = (
        contraction_sequence["decreasing"] is True
    )

    # Breakout qualification.
    breakout_pass = bool(
        breakout_result["breakout_confirmed"]
    )

    # ======================================
    # OVERALL SCREENING STATUS
    # ======================================

    core_conditions_pass = all([
        trend_pass,
        relative_strength_pass,
        vcp_sequence_pass
    ])

    if not core_conditions_pass:

        candidate_status = "NOT_QUALIFIED"

    elif breakout_pass:

        candidate_status = "BREAKOUT_CONFIRMED"

    else:

        candidate_status = "SETUP_WATCH"

    # ======================================
    # FINAL RESULT
    # ======================================

    result = {

        "symbol": symbol,

        "analysis_date": latest_date,

        "latest_price": round(
            latest_price, 2
        ),

        "data_info": {
            "stock_ticker": f"{symbol}.NS",
            "benchmark": "NIFTY 50",
            "stock_candles": int(len(stock_df)),
            "period": period,
            "latest_bar_source": (
                str(stock_df["DataSource"].iloc[-1])
                if "DataSource" in stock_df.columns
                else "Yahoo Finance auto-adjusted OHLCV"
            )
        },

        "swing_analysis": swing_result,

        "contraction_analysis": contraction_result,

        "trend_analysis": trend_result,

        "relative_strength_analysis": (
            relative_strength_result
        ),

        "breakout_analysis": breakout_result,

        "entry_exit_analysis": entry_exit_result,

        "screening_summary": {

            "trend_template_pass": trend_pass,

            "relative_strength_pass": (
                relative_strength_pass
            ),

            "vcp_sequence_pass": bool(
                vcp_sequence_pass
            ),

            "breakout_confirmed": breakout_pass,

            "core_conditions_pass": bool(
                core_conditions_pass
            ),

            "candidate_status": candidate_status
        },

        "decision_notes": [
            "This is a research screening result, not a trade recommendation.",
            "All numerical indicators are calculated by Python.",
            "Relative strength is a custom weighted comparison against Nifty 50.",
            "A true Minervini RS percentile requires a broad stock universe.",
            "Risk management and position sizing are not yet integrated.",
            "Manual trade approval is required.",
            "Entry and stop-loss calculations require confirmed breakout and valid swing data.",
            "Entry price is a reference based on the latest daily close.",
        ]
    }

    return result


# ==========================================
# MAIN
# ==========================================

if __name__ == "__main__":

    try:

        final_result = run_technical_analysis()

        print(
            "\n\n========== FINAL TECHNICAL ASSESSMENT ==========\n"
        )

        print(
            json.dumps(
                final_result,
                indent=4
            )
        )

        print(
            "\n========== SCREENING SUMMARY =========="
        )

        summary = final_result["screening_summary"]

        for key, value in summary.items():

            print(
                f"{key}: {value}"
            )

    except Exception as error:

        print("\nTECHNICAL ENGINE FAILED")

        print(str(error))

        traceback.print_exc()
