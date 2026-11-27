
import json
import pandas as pd

from market_data import fetch_stock_data


# ==========================================
# CONFIGURATION
# ==========================================

SYMBOL = "RELIANCE"
PERIOD = "2y"
SWING_WINDOW = 3
RECENT_SWINGS_LIMIT = 30


# ==========================================
# DATA VALIDATION
# ==========================================

def validate_data(df, window):

    required_columns = ["High", "Low"]

    for column in required_columns:
        if column not in df.columns:
            raise ValueError(
                f"Missing required column: {column}"
            )

    if window < 1:
        raise ValueError("Swing window must be at least 1")

    df = df.copy()

    df = df.dropna(
        subset=required_columns
    )

    if len(df) < (window * 2 + 1):
        raise ValueError("Not enough historical data")

    return df


# ==========================================
# SWING DETECTION
# ==========================================

def detect_swings(df, window=3):
    """
    Detect local swing highs and lows.

    Swing HIGH:
        Current high is greater than all previous
        window highs and greater than or equal to
        all subsequent window highs.

    Swing LOW:
        Current low is lower than all previous
        window lows and lower than or equal to
        all subsequent window lows.

    A swing is confirmed only after the subsequent
    window candles have completed.
    """

    df = df.copy()

    if len(df) < (2 * window + 1):
        return []

    highs = df["High"].tolist()
    lows = df["Low"].tolist()

    swings = []

    for i in range(window, len(df) - window):

        previous_highs = highs[i - window:i]
        next_highs = highs[i + 1:i + window + 1]

        previous_lows = lows[i - window:i]
        next_lows = lows[i + 1:i + window + 1]

        is_swing_high = (
            highs[i] > max(previous_highs)
            and highs[i] >= max(next_highs)
        )

        is_swing_low = (
            lows[i] < min(previous_lows)
            and lows[i] <= min(next_lows)
        )

        # Exclude candles that qualify as both.
        if is_swing_high and is_swing_low:
            continue

        if not is_swing_high and not is_swing_low:
            continue

        swing_type = (
            "HIGH" if is_swing_high else "LOW"
        )

        swing_price = (
            highs[i] if is_swing_high else lows[i]
        )

        swings.append({
            "index": int(i),
            "date": str(df.index[i].date()),
            "confirmation_date": str(
                df.index[i + window].date()
            ),
            "type": swing_type,
            "price": float(swing_price)
        })

    return swings


# ==========================================
# SWING NORMALIZATION
# ==========================================

def normalize_swings(swings):
    """
    Ensure alternating HIGH and LOW points.

    Consecutive HIGH:
        Keep the higher high.

    Consecutive LOW:
        Keep the lower low.

    This removes redundant swing points.
    """

    if not swings:
        return []

    normalized = []

    for swing in swings:

        current = swing.copy()

        if not normalized:
            normalized.append(current)
            continue

        previous = normalized[-1]

        # Different swing types: retain both.
        if current["type"] != previous["type"]:
            normalized.append(current)
            continue

        # Consecutive HIGH points:
        # Keep the highest price.
        if current["type"] == "HIGH":

            if current["price"] > previous["price"]:
                normalized[-1] = current

        # Consecutive LOW points:
        # Keep the lowest price.
        elif current["type"] == "LOW":

            if current["price"] < previous["price"]:
                normalized[-1] = current

    return normalized


# ==========================================
# SWING SUMMARY
# ==========================================

def build_summary(swings):

    high_count = sum(
        1 for swing in swings
        if swing["type"] == "HIGH"
    )

    low_count = sum(
        1 for swing in swings
        if swing["type"] == "LOW"
    )

    return {
        "swing_highs": high_count,
        "swing_lows": low_count
    }


# ==========================================
# MAIN ANALYSIS FUNCTION
# ==========================================

def analyse_swings(df, window=3):

    df = validate_data(df, window)

    raw_swings = detect_swings(
        df,
        window=window
    )

    normalized_swings = normalize_swings(
        raw_swings
    )

    summary = build_summary(
        normalized_swings
    )

    recent_swings = normalized_swings[
        -RECENT_SWINGS_LIMIT:
    ]

    return {
        "total_candles": int(len(df)),
        "window": int(window),
        "raw_swing_count": int(len(raw_swings)),
        "normalized_swing_count": int(
            len(normalized_swings)
        ),
        "swing_summary": summary,
        "recent_swings": recent_swings
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

    print(f"\nTotal candles: {len(df)}")

    print("\nDetecting swing points...")

    result = analyse_swings(
        df,
        window=SWING_WINDOW
    )

    output = {
        "symbol": SYMBOL,
        **result
    }

    print("\n===== SWING DETECTION RESULTS =====\n")

    print(
        json.dumps(
            output,
            indent=4
        )
    )

    print("\n===== SWING SUMMARY =====")

    print(
        "Raw swings:",
        result["raw_swing_count"]
    )

    print(
        "Normalized swings:",
        result["normalized_swing_count"]
    )

    print(
        "Swing highs:",
        result["swing_summary"]["swing_highs"]
    )

    print(
        "Swing lows:",
        result["swing_summary"]["swing_lows"]
    )
