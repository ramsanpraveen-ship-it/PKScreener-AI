"""Non-gating deterministic VCP, relative-strength, and breakout measurements."""
import pandas as pd

from relative_strength import RS_WEIGHTS


def _frame_as_of(frame, as_of=None):
    if not isinstance(frame, pd.DataFrame):
        frame = pd.DataFrame(frame)
    result = frame.copy()
    index = pd.DatetimeIndex(pd.to_datetime(result.index))
    if index.tz is not None:
        index = index.tz_localize(None)
    result.index = index.normalize()
    if result.index.has_duplicates:
        raise ValueError("Feature inputs must not contain duplicate dates")
    result = result.sort_index()
    if as_of is not None:
        result = result.loc[result.index <= pd.Timestamp(as_of).tz_localize(None).normalize()]
    return result


def _series_as_of(values, as_of=None):
    if isinstance(values, pd.DataFrame):
        if values.shape[1] != 1:
            raise ValueError("Expected a single close-price series")
        values = values.iloc[:, 0]
    result = _frame_as_of(pd.Series(values).to_frame("close"), as_of)["close"]
    result = pd.to_numeric(result, errors="coerce").dropna()
    return result.loc[result > 0]


def _true_range(frame):
    previous = frame["Close"].shift(1)
    return pd.concat([
        frame["High"] - frame["Low"],
        (frame["High"] - previous).abs(),
        (frame["Low"] - previous).abs(),
    ], axis=1).max(axis=1)


def _number(value):
    try:
        number = float(value)
        return number if pd.notna(number) else None
    except (TypeError, ValueError):
        return None


def measure_vcp_features(bars, contractions, pivot_price=None, as_of=None):
    """Return VCP geometry and volume observations, never a qualification gate."""
    frame = _frame_as_of(bars, as_of)
    required = {"High", "Low", "Close", "Volume"}
    if not required.issubset(frame.columns):
        raise ValueError("VCP feature frame requires High, Low, Close, Volume")
    frame = frame.dropna(subset=list(required))
    cutoff = frame.index[-1] if len(frame) else None

    usable = []
    for contraction in contractions or []:
        confirmed = contraction.get("confirmation_date") or contraction.get("end_date")
        if confirmed is not None and cutoff is not None:
            confirmed_date = pd.Timestamp(confirmed).tz_localize(None).normalize()
            if confirmed_date <= cutoff:
                usable.append(contraction)
    recent = usable[-3:]
    depths = [_number(item.get("depth_pct")) for item in recent]
    lows = [_number(item.get("low")) for item in recent]
    durations = [_number(item.get("duration_sessions")) for item in recent]
    volume_ratios = [_number(item.get("volume_analysis", {}).get("volume_ratio")) for item in recent]

    atr_pct = _true_range(frame).rolling(14, min_periods=14).mean().div(frame["Close"]).mul(100)
    contraction_atr = []
    for item in recent:
        start, end = item.get("start_date"), item.get("end_date")
        if start is None or end is None:
            contraction_atr.append(None)
            continue
        start = pd.Timestamp(start).tz_localize(None).normalize()
        end = pd.Timestamp(end).tz_localize(None).normalize()
        values = atr_pct.loc[(atr_pct.index >= start) & (atr_pct.index <= end)].dropna()
        contraction_atr.append(float(values.mean()) if len(values) else None)
    valid_atr = [value for value in contraction_atr if value is not None and value > 0]
    atr_ratio = valid_atr[-1] / valid_atr[0] if len(valid_atr) >= 2 else None

    close = float(frame["Close"].iloc[-1]) if len(frame) else None
    pivot_gap = (close / float(pivot_price) - 1) * 100 if close and _number(pivot_price) and float(pivot_price) > 0 else None
    high_252 = float(frame["High"].tail(252).max()) if len(frame) else None
    gap_from_high = (close / high_252 - 1) * 100 if close and high_252 and high_252 > 0 else None
    base_duration = None
    if recent and cutoff is not None and recent[0].get("start_date") is not None:
        base_start = pd.Timestamp(recent[0]["start_date"]).tz_localize(None).normalize()
        base_duration = int(((frame.index >= base_start) & (frame.index <= cutoff)).sum())

    known_depths = [value for value in depths if value is not None]
    known_lows = [value for value in lows if value is not None]
    known_volumes = [value for value in volume_ratios if value is not None]
    return {
        "as_of": cutoff.date().isoformat() if cutoff is not None else None,
        "contractions_observed": len(recent),
        "contraction_depths_pct_oldest_to_newest": known_depths,
        "depths_strictly_decreasing": all(known_depths[i] > known_depths[i + 1] for i in range(len(known_depths) - 1)) if len(known_depths) >= 2 else None,
        "contraction_lows_oldest_to_newest": known_lows,
        "higher_lows": all(known_lows[i] < known_lows[i + 1] for i in range(len(known_lows) - 1)) if len(known_lows) >= 2 else None,
        "contraction_durations_sessions": [int(value) for value in durations if value is not None],
        "base_duration_sessions": base_duration,
        "contraction_atr_pct": [round(value, 4) if value is not None else None for value in contraction_atr],
        "newest_to_oldest_contraction_atr_ratio": round(atr_ratio, 4) if atr_ratio is not None else None,
        "contraction_volume_ratios": [round(value, 4) for value in known_volumes],
        "average_contraction_volume_ratio": round(sum(known_volumes) / len(known_volumes), 4) if known_volumes else None,
        "close_to_pivot_pct": round(pivot_gap, 4) if pivot_gap is not None else None,
        "close_to_252_session_high_pct": round(gap_from_high, 4) if gap_from_high is not None else None,
        "measurements_only": True,
    }


def _relative_returns(stock, benchmark):
    data = pd.concat([stock.rename("stock"), benchmark.rename("benchmark")], axis=1, join="inner").dropna()
    scores = {}
    for label, sessions in (("3m", 63), ("6m", 126), ("9m", 189), ("12m", 252)):
        if len(data) <= sessions:
            scores[label] = None
        else:
            start, end = data.iloc[-sessions - 1], data.iloc[-1]
            stock_return = (end["stock"] / start["stock"] - 1) * 100
            benchmark_return = (end["benchmark"] / start["benchmark"] - 1) * 100
            scores[label] = float(stock_return - benchmark_return)
    return data, scores


def measure_relative_strength_features(stock_close, benchmark_close, eligible_universe=None, symbol=None, as_of=None):
    """Measure 3/6/12-month excess return, RS-line slope and internal percentile.

    The percentile is the rank of this module's legacy weighted excess-return
    score among the supplied point-in-time eligible symbols; it is not a
    vendor or Minervini RS rating. Historical sector membership is not present.
    """
    stock = _series_as_of(stock_close, as_of)
    benchmark = _series_as_of(benchmark_close, as_of)
    aligned, relative = _relative_returns(stock, benchmark)
    output = {
        "as_of": aligned.index[-1].date().isoformat() if len(aligned) else None,
        "periods": {},
        "rs_line_change_20d_pct": None,
        "legacy_weighted_relative_performance": None,
        "internal_cross_sectional_relative_percentile": None,
        "rank_universe_count": 0,
        "sector_relative_performance": None,
        "sector_relative_unavailable_reason": "Dated historical sector classifications were not provided",
    }
    for label in ("3m", "6m", "12m"):
        output["periods"][label] = {
            "relative_return_pct": round(relative[label], 4) if relative[label] is not None else None,
            "reason": None if relative[label] is not None else "Insufficient aligned completed sessions",
        }
    if len(aligned) >= 21:
        line = aligned["stock"] / aligned["benchmark"]
        output["rs_line_change_20d_pct"] = round(float((line.iloc[-1] / line.iloc[-21] - 1) * 100), 4)

    target = str(symbol or "").upper()
    if len(aligned) > 252:
        weighted = lambda values: sum(values[label] * weight for sessions, weight in RS_WEIGHTS.items()
                                      for label in ({63: "3m", 126: "6m", 189: "9m", 252: "12m"}[sessions],)
                                      if values.get(label) is not None)
        universe_scores = {}
        for name, values in (eligible_universe or {}).items():
            candidate = _series_as_of(values, as_of)
            _, scores = _relative_returns(candidate, benchmark)
            if all(scores.get(label) is not None for label in ("3m", "6m", "9m", "12m")):
                universe_scores[str(name).upper()] = weighted(scores)
        if target and target not in universe_scores and all(relative.get(key) is not None for key in ("3m", "6m", "9m", "12m")):
            universe_scores[target] = weighted(relative)
        output["rank_universe_count"] = len(universe_scores)
        if target in universe_scores and universe_scores:
            score = universe_scores[target]
            below = sum(value < score for value in universe_scores.values())
            equal = sum(value == score for value in universe_scores.values())
            output["legacy_weighted_relative_performance"] = round(score, 4)
            output["internal_cross_sectional_relative_percentile"] = round(100 * (below + 0.5 * equal) / len(universe_scores), 2)
    return output


def measure_breakout_features(bars, pivot_price, base_start_date=None, sector_confirmed=None, as_of=None):
    """Describe breakout context without changing the baseline breakout gate."""
    frame = _frame_as_of(bars, as_of)
    required = {"Open", "High", "Low", "Close", "Volume"}
    if not required.issubset(frame.columns):
        raise ValueError("Breakout feature frame requires Open, High, Low, Close, Volume")
    frame = frame.dropna(subset=list(required))
    if frame.empty:
        return {"as_of": None, "feature_status": "NO_DATA", "measurements_only": True}
    last = frame.iloc[-1]
    previous = frame.iloc[-2] if len(frame) > 1 else None
    base_volume = float(frame["Volume"].iloc[-21:-1].mean()) if len(frame) >= 21 else None
    rel_volume = float(last["Volume"]) / base_volume if base_volume and base_volume > 0 else None
    spread = float(last["High"] - last["Low"])
    close_position = (float(last["Close"] - last["Low"]) / spread) if spread > 0 else None
    atr = _true_range(frame).rolling(14, min_periods=14).mean()
    atr_pct = atr / frame["Close"] * 100
    recent_atr, prior_atr = atr_pct.iloc[-21:-1].dropna(), atr_pct.iloc[-41:-21].dropna()
    compression = float(recent_atr.mean() / prior_atr.mean()) if len(recent_atr) and len(prior_atr) and prior_atr.mean() > 0 else None
    close = float(last["Close"])
    pivot = _number(pivot_price)
    extension = (close / pivot - 1) * 100 if pivot and pivot > 0 else None
    open_gap = (float(last["Open"]) / float(previous["Close"]) - 1) * 100 if previous is not None and float(previous["Close"]) > 0 else None
    overhead = frame["High"].iloc[-253:-1]
    overhead = overhead.loc[overhead > close]
    resistance = float(overhead.min()) if len(overhead) else None
    traded_value = float((frame["Close"].tail(20) * frame["Volume"].tail(20)).mean()) if len(frame) >= 20 else None
    duration = None
    if base_start_date is not None:
        start = pd.Timestamp(base_start_date).tz_localize(None).normalize()
        duration = int((frame.index >= start).sum()) if start <= frame.index[-1] else 0
    return {
        "as_of": frame.index[-1].date().isoformat(),
        "relative_volume_20d": round(rel_volume, 4) if rel_volume is not None else None,
        "breakout_close_position": round(close_position, 4) if close_position is not None else None,
        "atr_pct_contraction_ratio_prior20_to_preceding20": round(compression, 4) if compression is not None else None,
        "base_duration_sessions": duration,
        "extension_from_pivot_pct": round(extension, 4) if extension is not None else None,
        "signal_open_gap_vs_previous_close_pct": round(open_gap, 4) if open_gap is not None else None,
        "next_session_gap_risk": None,
        "next_session_gap_unavailable_reason": "Future opening price is unknown at the signal close",
        "nearest_overhead_resistance": round(resistance, 4) if resistance is not None else None,
        "overhead_resistance_distance_pct": round((resistance / close - 1) * 100, 4) if resistance else None,
        "average_traded_value_20d": round(traded_value, 2) if traded_value is not None else None,
        "sector_confirmation": sector_confirmed,
        "sector_unavailable_reason": None if sector_confirmed is not None else "No dated historical sector classification/series provided",
        "measurements_only": True,
    }


def _true_range(frame):
    previous = frame["Close"].shift(1)
    return pd.concat([
        frame["High"] - frame["Low"],
        (frame["High"] - previous).abs(),
        (frame["Low"] - previous).abs(),
    ], axis=1).max(axis=1)
