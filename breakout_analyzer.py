
import json

from market_data import fetch_stock_data
from swing_detector import detect_swings


# ==========================================
# CONFIGURATION
# ==========================================

SYMBOL = "RELIANCE"
PERIOD = "2y"

SWING_WINDOW = 3
PIVOT_LOOKBACK = 60

VOLUME_BASELINE_PERIOD = 20
BREAKOUT_VOLUME_THRESHOLD = 1.5

BREAKOUT_BUFFER_PCT = 0.10
MAX_EXTENSION_PCT = 5.0
MIN_CLOSE_POSITION = 0.70


# ==========================================
# DATA VALIDATION
# ==========================================

def validate_data(df):

    required_columns = [
        "Open",
        "High",
        "Low",
        "Close",
        "Volume"
    ]

    for column in required_columns:
        if column not in df.columns:
            raise ValueError(
                f"Missing required column: {column}"
            )

    df = df.dropna(
        subset=required_columns
    ).copy()

    if len(df) < max(
        PIVOT_LOOKBACK,
        VOLUME_BASELINE_PERIOD + 2
    ):
        raise ValueError(
            "Insufficient historical data"
        )

    return df


# ==========================================
# IDENTIFY STRUCTURAL PIVOT
# ==========================================

def identify_pivot(df):

    # Exclude today's candle when identifying
    # historical resistance.
    historical_df = df.iloc[:-1].copy()

    swings = detect_swings(
        historical_df,
        window=SWING_WINDOW
    )

    minimum_index = max(
        0,
        len(historical_df) - PIVOT_LOOKBACK
    )

    recent_highs = [
        swing
        for swing in swings
        if (
            swing["type"] == "HIGH"
            and swing["index"] >= minimum_index
        )
    ]

    if not recent_highs:
        return None

    # Highest confirmed swing high in the lookback.
    pivot_swing = max(
        recent_highs,
        key=lambda item: item["price"]
    )

    return {
        "pivot_price": round(
            float(pivot_swing["price"]), 2
        ),
        "pivot_date": pivot_swing["date"],
        "confirmation_date": (
            pivot_swing["confirmation_date"]
        ),
        "pivot_type": "CONFIRMED_SWING_HIGH",
        "lookback_sessions": PIVOT_LOOKBACK
    }


# ==========================================
# CALCULATE VOLUME CONFIRMATION
# ==========================================

def analyse_breakout_volume(df):

    # Exclude the latest candle from the baseline.
    baseline = df["Volume"].iloc[
        -(VOLUME_BASELINE_PERIOD + 1):-1
    ]

    current_volume = float(
        df["Volume"].iloc[-1]
    )

    average_volume = float(
        baseline.mean()
    )

    if average_volume <= 0:
        return {
            "current_volume": current_volume,
            "average_volume": None,
            "volume_ratio": None,
            "volume_confirmed": False
        }

    volume_ratio = (
        current_volume / average_volume
    )

    return {
        "current_volume": round(
            current_volume, 2
        ),
        "average_volume": round(
            average_volume, 2
        ),
        "volume_ratio": round(
            volume_ratio, 2
        ),
        "volume_threshold": (
            BREAKOUT_VOLUME_THRESHOLD
        ),
        "volume_confirmed": bool(
            volume_ratio >= BREAKOUT_VOLUME_THRESHOLD
        )
    }


# ==========================================
# CANDLE QUALITY
# ==========================================

def analyse_candle_quality(latest):

    high = float(latest["High"])
    low = float(latest["Low"])
    close = float(latest["Close"])

    candle_range = high - low

    if candle_range <= 0:
        return {
            "close_position": None,
            "strong_close": False
        }

    close_position = (
        (close - low) / candle_range
    )

    return {
        "close_position": round(
            close_position, 3
        ),
        "minimum_required": MIN_CLOSE_POSITION,
        "strong_close": bool(
            close_position >= MIN_CLOSE_POSITION
        )
    }


# ==========================================
# BREAKOUT ANALYSIS
# ==========================================

def analyse_breakout(df, symbol=SYMBOL):

    df = validate_data(df)

    latest = df.iloc[-1]
    previous = df.iloc[-2]

    latest_close = float(
        latest["Close"]
    )

    previous_close = float(
        previous["Close"]
    )

    latest_date = str(
        df.index[-1].date()
    )

    pivot = identify_pivot(df)

    if pivot is None:

        return {
            "symbol": symbol,
            "date": latest_date,
            "status": "NO_STRUCTURAL_PIVOT",
            "breakout_confirmed": False,
            "reason": (
                "No confirmed swing high found "
                "in the pivot lookback period"
            )
        }

    pivot_price = pivot["pivot_price"]

    breakout_level = pivot_price * (
        1 + BREAKOUT_BUFFER_PCT / 100
    )

    volume = analyse_breakout_volume(df)

    candle = analyse_candle_quality(latest)

    price_above_pivot = (
        latest_close > pivot_price
    )

    crossed_today = (
        previous_close <= breakout_level
        and latest_close > breakout_level
    )

    extension_pct = (
        (latest_close / pivot_price) - 1
    ) * 100

    not_overextended = (
        extension_pct <= MAX_EXTENSION_PCT
    )

    # ======================================
    # DETERMINE BREAKOUT STATUS
    # ======================================

    if latest_close <= pivot_price:

        status = "BELOW_PIVOT"

        reason = (
            "Closing price is below structural pivot"
        )

    elif not crossed_today:

        status = "ABOVE_PIVOT_NOT_FRESH"

        reason = (
            "Price is above pivot but did not "
            "cross the breakout level today"
        )

    elif not volume["volume_confirmed"]:

        status = "UNCONFIRMED_LOW_VOLUME"

        reason = (
            "Price crossed pivot but breakout "
            "volume is below required threshold"
        )

    elif not candle["strong_close"]:

        status = "UNCONFIRMED_WEAK_CLOSE"

        reason = (
            "Price crossed pivot but candle "
            "did not close strongly"
        )

    elif not not_overextended:

        status = "OVEREXTENDED"

        reason = (
            "Price is too far above the estimated pivot"
        )

    else:

        status = "CONFIRMED_BREAKOUT"

        reason = (
            "Price crossed structural pivot with "
            "volume and candle confirmation"
        )

    breakout_confirmed = (
        status == "CONFIRMED_BREAKOUT"
    )

    return {

        "symbol": symbol,

        "date": latest_date,

        "price": round(
            latest_close, 2
        ),

        "previous_close": round(
            previous_close, 2
        ),

        "pivot": pivot,

        "breakout_level": round(
            breakout_level, 2
        ),

        "price_above_pivot": bool(
            price_above_pivot
        ),

        "crossed_pivot_today": bool(
            crossed_today
        ),

        "extension_from_pivot_pct": round(
            extension_pct, 2
        ),

        "not_overextended": bool(
            not_overextended
        ),

        "volume_analysis": volume,

        "candle_analysis": candle,

        "status": status,

        "breakout_confirmed": bool(
            breakout_confirmed
        ),

        "reason": reason,

        "limitations": [
            "Pivot is based on the highest confirmed swing high in the lookback",
            "Volume threshold is a configurable research assumption",
            "Breakout confirmation requires a completed daily candle",
            "No order or trade entry is generated"
        ]
    }


# ==========================================
# MAIN
# ==========================================

if __name__ == "__main__":

    print(
        f"Fetching historical data for {SYMBOL}..."
    )

    df = fetch_stock_data(
        SYMBOL,
        period=PERIOD
    )

    print(
        f"\nTotal candles: {len(df)}"
    )

    print(
        "\nAnalyzing structural breakout..."
    )

    result = analyse_breakout(df,symbol=SYMBOL)

    print(
        "\n========== BREAKOUT ANALYSIS ==========\n"
    )

    print(
        json.dumps(
            result,
            indent=4
        )
    )
