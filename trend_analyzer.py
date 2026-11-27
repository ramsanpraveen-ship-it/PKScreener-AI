
import json

from market_data import fetch_stock_data


# ==========================================
# CONFIGURATION
# ==========================================

DEFAULT_SYMBOL = "RELIANCE"
PERIOD = "2y"

SMA_SHORT = 50
SMA_MEDIUM = 150
SMA_LONG = 200

SMA_SLOPE_LOOKBACK = 20
WEEK_52_PERIOD = 252


# ==========================================
# DATA VALIDATION
# ==========================================

def validate_data(df):

    required_columns = ["Close", "High", "Low"]

    for column in required_columns:
        if column not in df.columns:
            raise ValueError(
                f"Missing required column: {column}"
            )

    df = df.dropna(
        subset=required_columns
    ).copy()

    if len(df) < SMA_LONG + SMA_SLOPE_LOOKBACK:
        raise ValueError(
            "Insufficient historical data for trend analysis"
        )

    return df


# ==========================================
# CALCULATE MOVING AVERAGES
# ==========================================

def calculate_moving_averages(df):

    df = df.copy()

    df["SMA50"] = df["Close"].rolling(
        SMA_SHORT
    ).mean()

    df["SMA150"] = df["Close"].rolling(
        SMA_MEDIUM
    ).mean()

    df["SMA200"] = df["Close"].rolling(
        SMA_LONG
    ).mean()

    return df


# ==========================================
# TREND TEMPLATE ANALYSIS
# ==========================================

def analyse_trend_template(
    df,
    symbol=DEFAULT_SYMBOL
):

    symbol = symbol.upper().strip()

    if not symbol:
        raise ValueError("Stock symbol cannot be empty")

    df = validate_data(df)
    df = calculate_moving_averages(df)

    latest = df.iloc[-1]

    previous_sma200 = df["SMA200"].iloc[
        -(SMA_SLOPE_LOOKBACK + 1)
    ]

    price = float(latest["Close"])

    sma50 = float(latest["SMA50"])
    sma150 = float(latest["SMA150"])
    sma200 = float(latest["SMA200"])

    recent_52w = df.tail(WEEK_52_PERIOD)

    high_52w = float(
        recent_52w["High"].max()
    )

    low_52w = float(
        recent_52w["Low"].min()
    )

    sma200_slope_pct = (
        (sma200 - float(previous_sma200))
        / float(previous_sma200)
    ) * 100

    # ======================================
    # INDIVIDUAL CONDITIONS
    # ======================================

    conditions = {

        "price_above_sma50": price > sma50,

        "price_above_sma150": price > sma150,

        "price_above_sma200": price > sma200,

        "sma50_above_sma150": sma50 > sma150,

        "sma50_above_sma200": sma50 > sma200,

        "sma150_above_sma200": sma150 > sma200,

        "sma200_trending_up": (
            sma200 > float(previous_sma200)
        ),

        "price_25pct_above_52w_low": (
            price >= low_52w * 1.25
        ),

        "price_within_25pct_of_52w_high": (
            price >= high_52w * 0.75
        )
    }

    passed = sum(
        1 for value in conditions.values()
        if value
    )

    total = len(conditions)

    all_conditions_pass = all(
        conditions.values()
    )

    overall_status = (
        "PENDING_RELATIVE_STRENGTH"
        if all_conditions_pass
        else "FAIL"
    )

    return {

        "symbol": symbol,

        "date": str(
            df.index[-1].date()
        ),

        "price": round(price, 2),

        "moving_averages": {

            "sma50": round(sma50, 2),

            "sma150": round(sma150, 2),

            "sma200": round(sma200, 2),

            "sma200_slope_pct": round(
                sma200_slope_pct, 2
            )
        },

        "52_week_range": {

            "high": round(high_52w, 2),

            "low": round(low_52w, 2)
        },

        "conditions": conditions,

        "conditions_passed": passed,

        "total_conditions": total,

        "trend_template_pass_without_rs": (
            bool(all_conditions_pass)
        ),

        "relative_strength_status": "PENDING",

        "overall_trend_template_status": (
            overall_status
        )
    }


# ==========================================
# MAIN
# ==========================================

if __name__ == "__main__":

    print(
        f"Fetching historical data for {DEFAULT_SYMBOL}..."
    )

    df = fetch_stock_data(
        DEFAULT_SYMBOL,
        period=PERIOD
    )

    print(f"\nTotal candles: {len(df)}")

    print("\nAnalyzing Minervini Trend Template...")

    result = analyse_trend_template(
        df,
        symbol=DEFAULT_SYMBOL
    )

    print("\n========== TREND ANALYSIS ==========\n")

    print(json.dumps(result, indent=4))