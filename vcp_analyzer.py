
import json
import pandas as pd

from market_data import fetch_stock_data


# ==========================================
# CONFIGURATION
# ==========================================

SYMBOL = "RELIANCE"
PERIOD = "2y"

SWING_WINDOW = 3
LOOKBACK = 120
MIN_CONTRACTIONS = 2

VOLUME_THRESHOLD = 1.0


# ==========================================
# 1. DETECT SWING HIGHS AND LOWS
# ==========================================

def detect_swings(df, window=3):

    swings = []

    for i in range(window, len(df) - window):

        high = float(df["High"].iloc[i])
        low = float(df["Low"].iloc[i])

        left_highs = df["High"].iloc[i-window:i]
        right_highs = df["High"].iloc[i+1:i+window+1]

        left_lows = df["Low"].iloc[i-window:i]
        right_lows = df["Low"].iloc[i+1:i+window+1]

        is_high = (
            high > left_highs.max()
            and high >= right_highs.max()
        )

        is_low = (
            low < left_lows.min()
            and low <= right_lows.min()
        )

        date = str(df.index[i].date())

        if is_high:
            swings.append({
                "date": date,
                "type": "HIGH",
                "price": round(high, 2),
                "index": i
            })

        if is_low:
            swings.append({
                "date": date,
                "type": "LOW",
                "price": round(low, 2),
                "index": i
            })

    return sorted(swings, key=lambda x: x["index"])


# ==========================================
# 2. NORMALIZE SWING POINTS
# ==========================================

def normalize_swings(swings):

    normalized = []

    for swing in swings:

        if not normalized:
            normalized.append(swing)
            continue

        previous = normalized[-1]

        if swing["type"] == previous["type"]:

            # Keep the more extreme point when two
            # consecutive swings have the same type.
            replace = (
                swing["price"] > previous["price"]
                if swing["type"] == "HIGH"
                else swing["price"] < previous["price"]
            )

            if replace:
                normalized[-1] = swing

        else:
            normalized.append(swing)

    return normalized


# ==========================================
# 3. CALCULATE CONTRACTION DEPTH
# ==========================================

def calculate_contractions(swings):

    contractions = []

    for i in range(len(swings) - 1):

        first = swings[i]
        second = swings[i + 1]

        if first["type"] == "HIGH" and second["type"] == "LOW":

            depth = (
                (first["price"] - second["price"])
                / first["price"]
            ) * 100

            if depth > 0:

                contractions.append({
                    "start_date": first["date"],
                    "end_date": second["date"],
                    "high": first["price"],
                    "low": second["price"],
                    "depth_pct": round(depth, 2),
                    "start_index": first["index"],
                    "end_index": second["index"]
                })

    return contractions


# ==========================================
# 4. CALCULATE VOLUME DRY-UP
# ==========================================

def analyse_contraction_volume(df, contractions):

    results = []

    for contraction in contractions:

        segment = df.iloc[
            contraction["start_index"]:
            contraction["end_index"] + 1
        ]

        avg_volume = segment["Volume"].mean()

        baseline = df["Volume"].iloc[
            max(0, contraction["start_index"] - 20):
            contraction["start_index"]
        ].mean()

        ratio = (
            avg_volume / baseline
            if pd.notna(baseline) and baseline > 0
            else None
        )

        results.append({
            "start_date": contraction["start_date"],
            "end_date": contraction["end_date"],
            "average_volume": round(float(avg_volume), 2),
            "baseline_volume": (
                round(float(baseline), 2)
                if pd.notna(baseline)
                else None
            ),
            "volume_ratio": (
                round(float(ratio), 2)
                if ratio is not None
                else None
            ),
            "volume_dry_up": (
                bool(ratio < VOLUME_THRESHOLD)
                if ratio is not None
                else None
            )
        })

    return results


# ==========================================
# 5. DETECT TREND ALIGNMENT
# ==========================================

def analyse_trend(df):

    latest = df.iloc[-1]

    return {
        "price_above_sma20": bool(
            latest["Close"] > latest["SMA20"]
        ),
        "price_above_sma50": bool(
            latest["Close"] > latest["SMA50"]
        ),
        "price_above_sma200": bool(
            latest["Close"] > latest["SMA200"]
        ),
        "sma20_above_sma50": bool(
            latest["SMA20"] > latest["SMA50"]
        ),
        "sma50_above_sma200": bool(
            latest["SMA50"] > latest["SMA200"]
        )
    }


# ==========================================
# 6. ANALYSE VCP
# ==========================================

def analyse_vcp(df):

    required = [
        "Open", "High", "Low", "Close", "Volume",
        "SMA20", "SMA50", "SMA200", "AVG_VOLUME20"
    ]

    missing_columns = [
        col for col in required if col not in df.columns
    ]

    if missing_columns:
        raise ValueError(f"Missing columns: {missing_columns}")

    df = df.dropna(subset=required).copy()

    if len(df) < 250:
        raise ValueError(
            f"Need 250 valid candles, received {len(df)}"
        )

    latest = df.iloc[-1]

    recent = df.tail(LOOKBACK).copy()

    swings = detect_swings(
        recent,
        window=SWING_WINDOW
    )

    swings = normalize_swings(swings)

    contractions = calculate_contractions(swings)

    contractions = contractions[-6:]

    # Contraction sequence should progressively reduce.
    depths = [
        item["depth_pct"]
        for item in contractions
    ]

    decreasing = (
        len(depths) >= MIN_CONTRACTIONS
        and all(
            depths[i] > depths[i + 1]
            for i in range(len(depths) - 1)
        )
    )

    volume_analysis = analyse_contraction_volume(
        recent,
        contractions
    )

    valid_volume = [
        item["volume_ratio"]
        for item in volume_analysis
        if item["volume_ratio"] is not None
    ]

    # Latest completed daily candle vs previous 20-day high.
    pivot = float(df["High"].iloc[-21:-1].max())

    close = float(latest["Close"])

    breakout = close > pivot

    volume_ratio = (
        float(latest["Volume"]) / float(latest["AVG_VOLUME20"])
        if latest["AVG_VOLUME20"] > 0
        else None
    )

    trend = analyse_trend(df)

    trend_pass = all(trend.values())

    vcp_structure = (
        decreasing
        and len(contractions) >= MIN_CONTRACTIONS
    )

    result = {
        "symbol": SYMBOL,

        "date": str(df.index[-1].date()),

        "price": round(close, 2),

        "trend_alignment": trend,

        "trend_template_pass": trend_pass,

        "swings_detected": len(swings),

        "contractions": [
            {
                "start_date": c["start_date"],
                "end_date": c["end_date"],
                "high": c["high"],
                "low": c["low"],
                "depth_pct": c["depth_pct"]
            }
            for c in contractions
        ],

        "contractions_decreasing": bool(decreasing),

        "vcp_structure_candidate": bool(vcp_structure),

        "contraction_volume_analysis": volume_analysis,

        "current_volume_ratio": (
            round(volume_ratio, 2)
            if volume_ratio is not None
            else None
        ),

        "estimated_pivot": round(pivot, 2),

        "price_above_estimated_pivot": bool(breakout),

        "breakout_status": (
            "PRICE_ABOVE_ESTIMATED_PIVOT"
            if breakout
            else "BELOW_ESTIMATED_PIVOT"
        ),

        "setup_quality": (
            "POTENTIAL_VCP"
            if vcp_structure and trend_pass
            else "NO_CLEAR_VCP"
        ),

        "limitations": [
            "Swing detection uses a retrospective three-candle window",
            "Pivot is a 20-day high, not a validated structural pivot",
            "Contraction pairing is a heuristic",
            "Trend template does not yet include relative strength",
            "No actual trade entry or stop-loss is calculated"
        ]
    }

    return result


# ==========================================
# 7. MAIN
# ==========================================

if __name__ == "__main__":

    print(f"\nFetching {SYMBOL} historical data...")

    df = fetch_stock_data(
        SYMBOL,
        period=PERIOD
    )

    result = analyse_vcp(df)

    print("\n========== VCP ANALYSIS ==========\n")

    print(json.dumps(result, indent=2))
