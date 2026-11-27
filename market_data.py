
import yfinance as yf
import pandas as pd
import requests
import io
import time
import hashlib
from pathlib import Path

from nse_calendar import get_latest_expected_nse_session, keep_completed_sessions


REQUIRED_COLUMNS = [
    "Open",
    "High",
    "Low",
    "Close",
    "Volume",
]

DOWNLOAD_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = 1.0
RECENT_DATA_FALLBACK_PERIOD = "1mo"
CACHE_DIR = Path(__file__).resolve().parent / "data" / "market_cache"


def _cache_path(symbol, period, interval):
    key = f"{symbol}|{period}|{interval}".encode("utf-8")
    return CACHE_DIR / f"{hashlib.sha256(key).hexdigest()[:24]}.csv"


def _load_fresh_cache(path, symbol):
    """Use only a valid cache whose newest candle is the expected session."""
    try:
        frame = pd.read_csv(path, index_col=0, parse_dates=True)
        frame = validate_ohlcv_data(frame, symbol)
        expected = get_latest_expected_nse_session()
        frame = keep_completed_sessions(frame, expected)
        if frame.empty or pd.Timestamp(frame.index[-1]).date() != expected:
            return None
        return frame
    except (OSError, ValueError, pd.errors.ParserError):
        return None


def _write_cache(path, frame):
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        columns = REQUIRED_COLUMNS + (["DataSource"] if "DataSource" in frame.columns else [])
        frame[columns].to_csv(temporary, index=True)
        temporary.replace(path)
    except OSError:
        # A cache write failure must never fail a valid market-data request.
        pass


def _download_with_retries(download, attempts=DOWNLOAD_ATTEMPTS, backoff=RETRY_BACKOFF_SECONDS, sleep=time.sleep):
    """Retry transient download/validation failures a bounded number of times."""
    last_error = None
    for attempt in range(attempts):
        try:
            return download()
        except Exception as error:
            last_error = error
            if attempt + 1 < attempts:
                sleep(backoff * (2 ** attempt))
    raise RuntimeError(f"DATA_DOWNLOAD_FAILED after {attempts} attempts: {last_error}") from last_error


def _parse_nse_bhavcopy(content, expected_session):
    """Parse an official NSE full bhavcopy and require its dated report rows."""
    if not content or content.lstrip().startswith(b"<"):
        raise ValueError("NSE bhavcopy response is empty or HTML, not CSV")
    frame = pd.read_csv(io.BytesIO(content))
    frame.columns = [str(column).strip() for column in frame.columns]
    required = {"SYMBOL", "SERIES", "DATE1", "OPEN_PRICE", "HIGH_PRICE",
                "LOW_PRICE", "CLOSE_PRICE", "TTL_TRD_QNTY"}
    if not required.issubset(frame.columns):
        raise ValueError(f"NSE bhavcopy is missing columns: {sorted(required - set(frame.columns))}")
    frame["SYMBOL"] = frame["SYMBOL"].astype(str).str.strip().str.upper()
    frame["SERIES"] = frame["SERIES"].astype(str).str.strip().str.upper()
    frame["_DATE"] = pd.to_datetime(frame["DATE1"].astype(str).str.strip(),
                                    format="%d-%b-%Y", errors="coerce").dt.normalize()
    expected = pd.Timestamp(expected_session).normalize()
    if not (frame["_DATE"] == expected).any():
        raise ValueError(f"NSE bhavcopy has no rows for expected session {expected.date()}")
    return frame


def _load_nse_bhavcopy(expected_session):
    """Load one exact-date official NSE bhavcopy, reusing a date-validated cache."""
    cache_path = CACHE_DIR / f"nse_bhavcopy_{expected_session:%d%m%Y}.csv"
    if cache_path.exists():
        try:
            content = cache_path.read_bytes()
            return _parse_nse_bhavcopy(content, expected_session)
        except (OSError, ValueError, pd.errors.ParserError):
            pass

    url = ("https://nsearchives.nseindia.com/products/content/"
           f"sec_bhavdata_full_{expected_session:%d%m%Y}.csv")
    response = requests.get(
        url, timeout=(5, 30),
        headers={"User-Agent": "Mozilla/5.0", "Accept": "text/csv,*/*"},
    )
    response.raise_for_status()
    content = response.content
    frame = _parse_nse_bhavcopy(content, expected_session)
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = cache_path.with_suffix(".csv.tmp")
        temporary.write_bytes(content)
        temporary.replace(cache_path)
    except OSError:
        # A cache write failure must not invalidate a validated official file.
        pass
    return frame


def _nse_eq_bar(symbol, expected_session):
    """Return a validated exact-session EQ candle from NSE's official report."""
    frame = _load_nse_bhavcopy(expected_session)
    rows = frame.loc[
        (frame["SYMBOL"] == symbol.upper())
        & (frame["SERIES"] == "EQ")
        & (frame["_DATE"] == pd.Timestamp(expected_session).normalize())
    ]
    if len(rows) != 1:
        raise ValueError(
            f"NSE bhavcopy has {len(rows)} EQ rows for {symbol} on {expected_session}"
        )
    row = rows.iloc[0]
    candle = pd.DataFrame(
        [{"Open": row["OPEN_PRICE"], "High": row["HIGH_PRICE"],
          "Low": row["LOW_PRICE"], "Close": row["CLOSE_PRICE"],
          "Volume": row["TTL_TRD_QNTY"]}],
        index=pd.DatetimeIndex([pd.Timestamp(expected_session)]),
    )
    candle = validate_ohlcv_data(candle, symbol)
    source_url = ("https://nsearchives.nseindia.com/products/content/"
                  f"sec_bhavdata_full_{expected_session:%d%m%Y}.csv")
    return candle, source_url


def _validated_adjustment_factor(raw_frame, expected_session):
    """Allow raw NSE OHLC into adjusted Yahoo history only with a stable factor."""
    if raw_frame.empty:
        raise ValueError("Yahoo adjustment check returned no recent candles")
    frame = normalize_yfinance_columns(raw_frame).copy()
    required = {"Close", "Adj Close", "Dividends", "Stock Splits"}
    if not required.issubset(frame.columns):
        raise ValueError("Yahoo adjustment check is missing close/action fields")
    for column in required:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    day = pd.Timestamp(expected_session).date()
    days = pd.Index(frame.index.date)
    valid_price = frame["Close"].gt(0) & frame["Adj Close"].gt(0)
    before_rows = frame.loc[(days < day) & valid_price]
    after_rows = frame.loc[(days > day) & valid_price]
    if before_rows.empty or after_rows.empty:
        raise ValueError("Yahoo adjustment check needs prices on both sides of the missing session")
    before = before_rows.iloc[-1]
    after = after_rows.iloc[0]
    before_day = before_rows.index[-1].date()
    after_day = after_rows.index[0].date()
    if (day - before_day).days > 4 or (after_day - day).days > 4:
        raise ValueError("Yahoo adjustment reference dates are too far from the missing session")
    action_window = frame.loc[(days >= before_day) & (days <= after_day)]
    if action_window[["Dividends", "Stock Splits"]].isna().any().any():
        raise ValueError("Yahoo corporate-action fields are incomplete near the missing session")
    if action_window["Dividends"].ne(0).any() or action_window["Stock Splits"].ne(0).any():
        raise ValueError("Yahoo reports a nearby corporate action; NSE fallback is unsafe")
    factors = [float(before["Adj Close"] / before["Close"]),
               float(after["Adj Close"] / after["Close"])]
    if not all(pd.notna(value) and value > 0 for value in factors):
        raise ValueError("Yahoo adjustment factors are invalid")
    if abs(factors[0] - factors[1]) > 1e-10 * max(1.0, abs(factors[0]), abs(factors[1])):
        raise ValueError("Yahoo adjustment factor changes across the missing session")
    return factors[0]


def normalize_yfinance_columns(df):
    """
    Normalize yfinance columns, including MultiIndex responses.
    """

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df.loc[:, ~df.columns.duplicated()].copy()

    return df


def validate_ohlcv_data(df, symbol):
    """
    Validate daily OHLCV data and remove incomplete candles.
    """

    missing_columns = [
        column
        for column in REQUIRED_COLUMNS
        if column not in df.columns
    ]

    if missing_columns:
        raise ValueError(
            f"{symbol}: Missing columns: {missing_columns}"
        )

    original_count = len(df)

    # Convert market data columns to numeric.
    for column in REQUIRED_COLUMNS:
        df[column] = pd.to_numeric(
            df[column],
            errors="coerce"
        )

    # Remove rows with missing OHLCV values.
    df = df.dropna(
        subset=REQUIRED_COLUMNS
    ).copy()

    # Remove invalid prices and volumes.
    valid_prices = (
        (df["Open"] > 0)
        & (df["High"] > 0)
        & (df["Low"] > 0)
        & (df["Close"] > 0)
        & (df["Volume"] >= 0)
    )

    df = df.loc[valid_prices].copy()

    # Validate candle price relationships.
    valid_candles = (
        (df["High"] >= df["Low"])
        & (df["High"] >= df["Open"])
        & (df["High"] >= df["Close"])
        & (df["Low"] <= df["Open"])
        & (df["Low"] <= df["Close"])
    )

    df = df.loc[valid_candles].copy()

    # Remove duplicate dates and sort chronologically.
    df = df.loc[~df.index.duplicated(keep="last")]
    df = df.sort_index()

    removed_count = original_count - len(df)

    print(
        f"{symbol}: Received {original_count} candles, "
        f"valid {len(df)}, removed {removed_count}"
    )

    if df.empty:
        raise ValueError(
            f"{symbol}: No valid OHLCV candles available"
        )

    return df


def fetch_stock_data(
    symbol,
    period="2y",
    interval="1d"
):
    """
    Download and prepare NSE stock daily market data.

    Note:
    Yahoo Finance data is not guaranteed to be real-time
    or complete for the latest trading session.
    """

    ticker = f"{symbol}.NS"

    cache_path = _cache_path(symbol, period, interval)
    if interval == "1d":
        cached = _load_fresh_cache(cache_path, symbol)
        if cached is not None:
            df = cached
            df["SMA20"] = df["Close"].rolling(20).mean()
            df["SMA50"] = df["Close"].rolling(50).mean()
            df["SMA200"] = df["Close"].rolling(200).mean()
            df["AVG_VOLUME20"] = df["Volume"].rolling(20).mean()
            df["ATR"] = calculate_atr(df)
            return df

    print(f"Downloading market data: {ticker}")

    def download_period(requested_period):
        frame = yf.download(ticker, period=requested_period, interval=interval,
                            auto_adjust=True, progress=False, threads=False)
        if frame.empty:
            raise ValueError(f"No data found for {ticker} ({requested_period})")
        return validate_ohlcv_data(normalize_yfinance_columns(frame), symbol)

    def download_and_validate():
        frame = download_period(period)
        if interval == "1d":
            expected = get_latest_expected_nse_session()
            frame = keep_completed_sessions(frame, expected)
            latest = None if frame.empty else pd.Timestamp(frame.index[-1]).date()

            if latest != expected:
                # A short Yahoo request may contain a row omitted from its
                # long-range response. Prefer that same-source history first.
                recent = download_period(RECENT_DATA_FALLBACK_PERIOD)
                recent = keep_completed_sessions(recent, expected)
                recent_latest = None if recent.empty else pd.Timestamp(recent.index[-1]).date()
                if recent_latest == expected:
                    older = frame.loc[frame.index < recent.index[0]]
                    frame = pd.concat([older, recent]).sort_index()
                    latest = pd.Timestamp(frame.index[-1]).date()
                else:
                    # Last resort: official NSE EOD row, only after a stable
                    # Yahoo adjustment factor is independently demonstrated.
                    raw_recent = yf.download(
                        ticker, period=RECENT_DATA_FALLBACK_PERIOD, interval=interval,
                        auto_adjust=False, actions=True, progress=False, threads=False
                    )
                    factor = _validated_adjustment_factor(raw_recent, expected)
                    official, source_url = _nse_eq_bar(symbol, expected)
                    official.loc[:, ["Open", "High", "Low", "Close"]] *= factor
                    official["DataSource"] = (
                        f"NSE official EOD ({source_url}); Yahoo adjustment factor {factor:.12g}"
                    )
                    expected_timestamp = pd.Timestamp(expected)
                    recent_start = (
                        recent.index[0] if not recent.empty else expected_timestamp
                    )
                    older = frame.loc[frame.index < recent_start]
                    recent_before = recent.loc[recent.index < expected_timestamp]
                    frame = pd.concat([older, recent_before, official]).sort_index()
                    frame["DataSource"] = "Yahoo Finance auto-adjusted OHLCV"
                    frame.loc[official.index[0], "DataSource"] = official["DataSource"].iloc[0]
                    latest = pd.Timestamp(frame.index[-1]).date()

            if latest != expected:
                raise ValueError(f"STALE_DATA: {symbol} latest={latest} expected={expected}")
            if "DataSource" not in frame.columns:
                frame["DataSource"] = "Yahoo Finance auto-adjusted OHLCV"
        return frame

    df = _download_with_retries(download_and_validate)
    if interval == "1d":
        _write_cache(cache_path, df)

    # Technical indicators.
    df["SMA20"] = df["Close"].rolling(20).mean()

    df["SMA50"] = df["Close"].rolling(50).mean()

    df["SMA200"] = df["Close"].rolling(200).mean()

    df["AVG_VOLUME20"] = (
        df["Volume"].rolling(20).mean()
    )

    df["ATR"] = calculate_atr(df)

    return df


def calculate_atr(df, period=14):
    """
    Calculate Average True Range.
    """

    previous_close = df["Close"].shift(1)

    high_low = df["High"] - df["Low"]

    high_previous = (
        df["High"] - previous_close
    ).abs()

    low_previous = (
        df["Low"] - previous_close
    ).abs()

    true_range = pd.concat(
        [
            high_low,
            high_previous,
            low_previous,
        ],
        axis=1
    ).max(axis=1)

    return true_range.rolling(
        period
    ).mean()


def validate_common_latest_date(
    stock_df,
    benchmark_df
):
    """
    Verify that stock and benchmark data end
    on the same valid trading date.

    This does NOT establish that the date is the
    latest expected NSE trading session.
    """

    if stock_df.empty or benchmark_df.empty:
        raise ValueError(
            "Stock or benchmark data is empty"
        )

    stock_date = pd.Timestamp(
        stock_df.index[-1]
    ).date()

    benchmark_date = pd.Timestamp(
        benchmark_df.index[-1]
    ).date()

    if stock_date != benchmark_date:
        raise ValueError(
            "Market data date mismatch: "
            f"Stock={stock_date}, "
            f"Benchmark={benchmark_date}"
        )

    return stock_date


# ==========================================
# MAIN
# ==========================================

if __name__ == "__main__":

    data = fetch_stock_data(
        "RELIANCE",
        period="1mo"
    )

    print("\n========== MARKET DATA VALIDATION ==========")

    print("Total valid candles:", len(data))

    print(
        "Valid SMA200 candles:",
        data["SMA200"].notna().sum()
    )

    print("First date:", data.index.min())

    print("Latest valid date:", data.index.max())

    print("\nLatest five candles:")

    print(
        data.tail(5).to_string()
    )
