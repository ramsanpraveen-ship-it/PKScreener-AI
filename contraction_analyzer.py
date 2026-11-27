
import json

from market_data import fetch_stock_data
from swing_detector import analyse_swings, SWING_WINDOW


# ==========================================
# CONFIGURATION
# ==========================================

SYMBOL = "RELIANCE"
PERIOD = "2y"

LOOKBACK_CANDLES = 180
VOLUME_BASELINE_PERIOD = 20

MIN_CONTRACTIONS_FOR_PATTERN = 3


# ==========================================
# DATA VALIDATION
# ==========================================

def validate_data(df):

    required_columns = [
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

    return df


# ==========================================
# CALCULATE CONTRACTION DEPTH
# ==========================================

def calculate_depth(high, low):

    if high <= 0 or low <= 0 or low > high:
        return None

    depth = ((high - low) / high) * 100

    return round(float(depth), 2)


# ==========================================
# ANALYSE CONTRACTION VOLUME
# ==========================================

def analyse_contraction_volume(
    df,
    high_index,
    low_index
):

    baseline_start = (
        high_index - VOLUME_BASELINE_PERIOD
    )

    if baseline_start < 0:
        return {
            "average_volume": None,
            "baseline_volume": None,
            "volume_ratio": None,
            "volume_dry_up": None,
            "reason": "Insufficient baseline history"
        }

    if low_index < high_index:
        return {
            "average_volume": None,
            "baseline_volume": None,
            "volume_ratio": None,
            "volume_dry_up": None,
            "reason": "Invalid contraction indices"
        }

    # Volume during the contraction.
    contraction_volume = df["Volume"].iloc[
        high_index:low_index + 1
    ]

    # Volume during the 20 sessions before
    # the contraction starts.
    baseline_volume = df["Volume"].iloc[
        baseline_start:high_index
    ]

    if contraction_volume.empty or baseline_volume.empty:
        return {
            "average_volume": None,
            "baseline_volume": None,
            "volume_ratio": None,
            "volume_dry_up": None,
            "reason": "Insufficient volume observations"
        }

    average_volume = float(
        contraction_volume.mean()
    )

    baseline_average = float(
        baseline_volume.mean()
    )

    if baseline_average <= 0:
        return {
            "average_volume": round(average_volume, 2),
            "baseline_volume": None,
            "volume_ratio": None,
            "volume_dry_up": None,
            "reason": "Invalid baseline volume"
        }

    volume_ratio = (
        average_volume / baseline_average
    )

    return {
        "average_volume": round(average_volume, 2),
        "baseline_volume": round(baseline_average, 2),
        "volume_ratio": round(volume_ratio, 2),
        "volume_dry_up": bool(volume_ratio < 1.0),
        "reason": None
    }


# ==========================================
# IDENTIFY HIGH-TO-LOW CONTRACTIONS
# ==========================================

def identify_contractions(df, swings):

    contractions = []

    for i in range(len(swings) - 1):

        high_swing = swings[i]
        low_swing = swings[i + 1]

        # Only consider HIGH followed by LOW.
        if high_swing["type"] != "HIGH":
            continue

        if low_swing["type"] != "LOW":
            continue

        high_index = high_swing["index"]
        low_index = low_swing["index"]

        if low_index <= high_index:
            continue

        high_price = float(
            high_swing["price"]
        )

        low_price = float(
            low_swing["price"]
        )

        depth = calculate_depth(
            high_price,
            low_price
        )

        if depth is None:
            continue

        duration = int(
            low_index - high_index
        )

        volume_analysis = analyse_contraction_volume(
            df,
            high_index,
            low_index
        )

        contractions.append({
            "start_date": high_swing["date"],
            "end_date": low_swing["date"],
            "confirmation_date": low_swing["confirmation_date"],
            "high": round(high_price, 2),
            "low": round(low_price, 2),
            "depth_pct": depth,
            "duration_sessions": duration,
            "volume_analysis": volume_analysis
        })

    return contractions


# ==========================================
# CHECK DECREASING CONTRACTIONS
# ==========================================

def analyse_contraction_sequence(contractions):

    # Evaluate the latest three contractions.
    recent = contractions[
        -MIN_CONTRACTIONS_FOR_PATTERN:
    ]

    if len(recent) < MIN_CONTRACTIONS_FOR_PATTERN:

        return {
            "evaluated_contractions": len(recent),
            "decreasing": None,
            "reason": (
                "At least three contractions are required"
            )
        }

    depths = [
        item["depth_pct"]
        for item in recent
    ]

    decreasing = all(
        depths[i] > depths[i + 1]
        for i in range(len(depths) - 1)
    )

    return {
        "evaluated_contractions": len(recent),
        "depths_pct": depths,
        "decreasing": bool(decreasing),
        "reason": None if decreasing else (
            "Contraction depths are not progressively decreasing"
        )
    }


# ==========================================
# ANALYSE VOLUME DRY-UP
# ==========================================

def analyse_volume_dry_up(contractions):

    valid_ratios = [
        item["volume_analysis"]["volume_ratio"]
        for item in contractions
        if item["volume_analysis"]["volume_ratio"] is not None
    ]

    if not valid_ratios:
        return {
            "average_volume_ratio": None,
            "dry_up_contractions": 0,
            "total_contractions": len(contractions),
            "status": "UNKNOWN"
        }

    dry_up_count = sum(
        1 for ratio in valid_ratios
        if ratio < 1.0
    )

    average_ratio = sum(valid_ratios) / len(valid_ratios)

    return {
        "average_volume_ratio": round(
            average_ratio, 2
        ),
        "dry_up_contractions": dry_up_count,
        "total_contractions": len(valid_ratios),
        "status": (
            "VOLUME_DRY_UP"
            if dry_up_count >= 2 and average_ratio < 1.0
            else "NO_CLEAR_VOLUME_DRY_UP"
        )
    }


# ==========================================
# MAIN CONTRACTION ANALYSIS
# ==========================================

def analyse_contractions(df, symbol=SYMBOL):

    df = validate_data(df)

    # Use recent history for VCP structure.
    recent_df = df.tail(
        LOOKBACK_CANDLES
    ).copy()

    # Detect and normalize swings using existing module.
    swing_result = analyse_swings(
        recent_df,
        window=SWING_WINDOW
    )

    swings = swing_result["recent_swings"]

    contractions = identify_contractions(
        recent_df,
        swings
    )

    sequence_analysis = analyse_contraction_sequence(
        contractions
    )

    volume_analysis = analyse_volume_dry_up(
        contractions
    )

    return {
        "symbol": symbol,
        "candles_analyzed": int(len(recent_df)),
        "swings_used": len(swings),
        "contraction_count": len(contractions),
        "contractions": contractions,
        "contraction_sequence": sequence_analysis,
        "volume_analysis": volume_analysis
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
        f"\nTotal candles fetched: {len(df)}"
    )

    print("\nAnalyzing contraction structures...")

    result = analyse_contractions(df)

    print(
        "\n========== CONTRACTION ANALYSIS ==========\n"
    )

    print(
        json.dumps(
            result,
            indent=4
        )
    )
