
import yfinance as yf
import pandas as pd
import time
from nse_calendar import get_latest_expected_nse_session, keep_completed_sessions


INDEX_SYMBOL = "^NSEI"

# Relative-strength weighting
RS_WEIGHTS = {
    63: 0.40,
    126: 0.20,
    189: 0.20,
    252: 0.20,
}


def fetch_close_prices(ticker, period="2y", attempts=3, backoff=1.0, sleep=time.sleep):
    """Fetch adjusted daily closing prices."""
    expected_date = get_latest_expected_nse_session()
    last_error = None
    for attempt in range(attempts):
        try:
            df = yf.download(ticker, period=period, interval="1d",
                             auto_adjust=True, progress=False, threads=False)
            if df.empty:
                raise ValueError(f"No market data available for {ticker}")
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            if "Close" not in df.columns:
                raise ValueError(f"Close price missing for {ticker}")
            close = pd.to_numeric(df["Close"], errors="coerce").dropna()
            if close.empty or (close <= 0).any():
                raise ValueError(f"No valid positive closing prices for {ticker}")
            close = close.loc[~close.index.duplicated(keep="last")].sort_index()
            close = keep_completed_sessions(close, expected_date)
            latest_date = None if close.empty else pd.Timestamp(close.index[-1]).date()
            if latest_date != expected_date:
                raise ValueError(f"STALE_DATA: {ticker} latest={latest_date} expected={expected_date}")
            close.name = ticker
            return close
        except Exception as error:
            last_error = error
            if attempt + 1 < attempts:
                sleep(backoff * (2 ** attempt))
    raise RuntimeError(f"DATA_DOWNLOAD_FAILED after {attempts} attempts for {ticker}: {last_error}") from last_error


def prepare_data(stock, benchmark):
    """Align stock and benchmark closing prices by trading date."""

    stock = pd.Series(stock).dropna().copy()
    benchmark = pd.Series(benchmark).dropna().copy()

    data = pd.concat(
        [stock, benchmark],
        axis=1,
        join="inner"
    ).dropna()

    if data.empty:
        raise ValueError("No overlapping stock and benchmark dates")

    if len(data) < 253:
        raise ValueError(
            f"At least 253 aligned trading sessions are required. "
            f"Available: {len(data)}"
        )

    if (data <= 0).any().any():
        raise ValueError("Closing prices must be positive")

    return data


def calculate_period_returns(data, stock_ticker):
    """Calculate stock and benchmark returns over different periods."""

    benchmark_ticker = INDEX_SYMBOL

    periods = {
        "3m": 63,
        "6m": 126,
        "9m": 189,
        "12m": 252,
    }

    results = {}

    for label, sessions in periods.items():

        stock_start = data[stock_ticker].iloc[-sessions - 1]
        stock_end = data[stock_ticker].iloc[-1]

        benchmark_start = data[benchmark_ticker].iloc[-sessions - 1]
        benchmark_end = data[benchmark_ticker].iloc[-1]

        stock_return = (
            (stock_end / stock_start) - 1
        ) * 100

        benchmark_return = (
            (benchmark_end / benchmark_start) - 1
        ) * 100

        relative_return = stock_return - benchmark_return

        results[label] = {
            "sessions": sessions,
            "stock_return": round(float(stock_return), 2),
            "benchmark_return": round(float(benchmark_return), 2),
            "relative_return": round(float(relative_return), 2),
            "outperformed": bool(relative_return > 0),
        }

    return results


def calculate_weighted_relative_strength(period_returns):
    """Calculate weighted relative performance."""

    weighted_score = 0.0

    labels = {
        63: "3m",
        126: "6m",
        189: "9m",
        252: "12m",
    }

    for sessions, weight in RS_WEIGHTS.items():

        label = labels[sessions]

        weighted_score += (
            period_returns[label]["relative_return"] * weight
        )

    return round(weighted_score, 2)


def analyse_rs_line(data, stock_ticker):
    """Analyse the stock-to-index relative-strength line."""

    benchmark_ticker = INDEX_SYMBOL

    rs_line = (
        data[stock_ticker] / data[benchmark_ticker]
    )

    current_rs = float(rs_line.iloc[-1])
    previous_rs = float(rs_line.iloc[-21])

    change_20d = (
        (current_rs / previous_rs) - 1
    ) * 100

    return {
        "current_rs_line": round(current_rs, 4),
        "change_20d_percent": round(float(change_20d), 2),
        "rs_line_rising": bool(change_20d > 0),
    }


def analyse_relative_strength_from_data(
    stock,
    benchmark,
    symbol="RELIANCE"
):
    """
    Analyse relative strength using already-fetched data.

    The symbol is passed dynamically so results cannot accidentally
    be labelled as RELIANCE when analysing another stock.
    """

    symbol = symbol.upper().strip()
    stock_ticker = f"{symbol}.NS"

    stock = pd.Series(stock).copy()
    benchmark = pd.Series(benchmark).copy()

    stock.name = stock_ticker
    benchmark.name = INDEX_SYMBOL

    data = prepare_data(stock, benchmark)

    period_returns = calculate_period_returns(
        data,
        stock_ticker
    )

    weighted_score = calculate_weighted_relative_strength(
        period_returns
    )

    rs_line = analyse_rs_line(
        data,
        stock_ticker
    )

    outperforming_periods = sum(
        1
        for result in period_returns.values()
        if result["outperformed"]
    )

    return {
        "symbol": symbol,
        "stock_ticker": stock_ticker,
        "benchmark": INDEX_SYMBOL,
        "period_returns": period_returns,
        "weighted_relative_performance": weighted_score,
        "outperforming_periods": outperforming_periods,
        "rs_line": rs_line,
        "relative_strength_pass": bool(
            weighted_score > 0
            and outperforming_periods >= 2
            and rs_line["rs_line_rising"]
        ),
    }


def analyse_relative_strength(symbol="RELIANCE", period="2y"):
    """Standalone analysis that fetches stock and benchmark data."""

    symbol = symbol.upper().strip()

    stock_ticker = f"{symbol}.NS"

    stock = fetch_close_prices(
        stock_ticker,
        period=period
    )

    benchmark = fetch_close_prices(
        INDEX_SYMBOL,
        period=period
    )

    return analyse_relative_strength_from_data(
        stock,
        benchmark,
        symbol=symbol
    )


if __name__ == "__main__":

    result = analyse_relative_strength(
        symbol="RELIANCE",
        period="2y"
    )

    print("\nRELATIVE STRENGTH ANALYSIS")
    print("=" * 40)

    print("Symbol:", result["symbol"])
    print(
        "Weighted relative performance:",
        result["weighted_relative_performance"],
        "%"
    )

    print(
        "Outperforming periods:",
        result["outperforming_periods"],
        "/ 4"
    )

    print("RS line:", result["rs_line"])
    print(
        "Relative strength pass:",
        result["relative_strength_pass"]
    )
