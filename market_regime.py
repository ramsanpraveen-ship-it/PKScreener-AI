"""Point-in-time market regime and breadth measurements (descriptive only)."""
import pandas as pd


def _close_series(values, as_of=None):
    series = pd.to_numeric(pd.Series(values), errors="coerce")
    index = pd.DatetimeIndex(pd.to_datetime(series.index))
    if index.tz is not None:
        index = index.tz_localize(None)
    series.index = index.normalize()
    if series.index.has_duplicates:
        raise ValueError("Market regime inputs must not contain duplicate dates")
    series = series.sort_index().dropna()
    series = series.loc[series > 0]
    if as_of is not None:
        cutoff = pd.Timestamp(as_of).tz_localize(None).normalize()
        series = series.loc[series.index <= cutoff]
    return series


def analyze_market_regime(benchmark_close, eligible_symbols, point_in_time_stock_closes, as_of=None):
    """Measure Nifty 50 trend and breadth using data available through as_of.

    eligible_symbols must be sourced point-in-time EQ membership. If it is not
    supplied, breadth is unavailable instead of falling back to current members.
    """
    benchmark = _close_series(benchmark_close, as_of)
    result = {
        "as_of": benchmark.index[-1].date().isoformat() if len(benchmark) else None,
        "classification": "INSUFFICIENT_HISTORY",
        "benchmark": "NIFTY_50_PRICE_INDEX",
        "benchmark_close": None,
        "sma_50": None,
        "sma_200": None,
        "sma_200_slope_20d_pct": None,
        "above_sma_50": None,
        "above_sma_200": None,
        "breadth_pct_above_50d": None,
        "breadth_pct_above_200d": None,
        "breadth_eligible_count": 0,
        "breadth_measured_50d": 0,
        "breadth_measured_200d": 0,
        "breadth_unavailable_reason": None,
    }
    if len(benchmark) >= 200:
        sma50 = float(benchmark.rolling(50).mean().iloc[-1])
        sma200 = float(benchmark.rolling(200).mean().iloc[-1])
        slope = None
        if len(benchmark) >= 220:
            prior_sma200 = float(benchmark.rolling(200).mean().iloc[-21])
            if prior_sma200 > 0:
                slope = (sma200 / prior_sma200 - 1) * 100
        close = float(benchmark.iloc[-1])
        if slope is None:
            regime = "INSUFFICIENT_SLOPE_HISTORY"
        elif close > sma50 and close > sma200 and slope > 0:
            regime = "BULLISH"
        elif close < sma50 and close < sma200 and slope < 0:
            regime = "BEARISH"
        else:
            regime = "NEUTRAL"
        result.update({
            "classification": regime,
            "benchmark_close": close,
            "sma_50": sma50,
            "sma_200": sma200,
            "sma_200_slope_20d_pct": slope,
            "above_sma_50": close > sma50,
            "above_sma_200": close > sma200,
        })

    if not eligible_symbols:
        result["breadth_unavailable_reason"] = "Point-in-time eligible symbol list is required"
        return result

    eligible = sorted(set(str(symbol).upper() for symbol in eligible_symbols))
    above50 = measured50 = above200 = measured200 = 0
    for symbol in eligible:
        values = point_in_time_stock_closes.get(symbol)
        if values is None:
            continue
        close = _close_series(values, as_of)
        if len(close) >= 50:
            measured50 += 1
            above50 += int(float(close.iloc[-1]) > float(close.rolling(50).mean().iloc[-1]))
        if len(close) >= 200:
            measured200 += 1
            above200 += int(float(close.iloc[-1]) > float(close.rolling(200).mean().iloc[-1]))
    result.update({
        "breadth_eligible_count": len(eligible),
        "breadth_measured_50d": measured50,
        "breadth_measured_200d": measured200,
        "breadth_pct_above_50d": round(100 * above50 / measured50, 2) if measured50 else None,
        "breadth_pct_above_200d": round(100 * above200 / measured200, 2) if measured200 else None,
        "breadth_unavailable_reason": None if measured200 else "No eligible symbols have 200 completed sessions",
    })
    return result
