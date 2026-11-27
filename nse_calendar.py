
from datetime import datetime, date, time, timedelta
from zoneinfo import ZoneInfo


IST = ZoneInfo("Asia/Kolkata")

# Official NSE Capital Market holidays for 2026.
NSE_HOLIDAYS_2026 = {
    date(2026, 1, 26),
    date(2026, 3, 3),
    date(2026, 3, 26),
    date(2026, 3, 31),
    date(2026, 4, 3),
    date(2026, 4, 14),
    date(2026, 5, 1),
    date(2026, 5, 28),
    date(2026, 6, 26),
    date(2026, 9, 14),
    date(2026, 10, 2),
    date(2026, 10, 20),
    date(2026, 11, 10),
    date(2026, 11, 24),
    date(2026, 12, 25),
}

# Special trading session: Diwali Muhurat trading.
NSE_SPECIAL_TRADING_DAYS_2026 = {
    date(2026, 11, 8),
}

# Consider a daily candle complete only after this time.
DATA_PUBLICATION_TIME = time(16, 0)


def is_nse_trading_day(check_date):

    if check_date.year != 2026:
        raise ValueError(
            f"NSE calendar not configured for {check_date.year}"
        )

    if check_date in NSE_SPECIAL_TRADING_DAYS_2026:
        return True

    if check_date.weekday() >= 5:
        return False

    if check_date in NSE_HOLIDAYS_2026:
        return False

    return True


def get_latest_expected_nse_session(now=None):

    if now is None:
        now = datetime.now(IST)

    elif now.tzinfo is None:
        now = now.replace(tzinfo=IST)

    else:
        now = now.astimezone(IST)

    candidate = now.date()

    # Before publication time, today's candle
    # is not considered complete.
    if (
        is_nse_trading_day(candidate)
        and now.time() < DATA_PUBLICATION_TIME
    ):
        candidate -= timedelta(days=1)

    while not is_nse_trading_day(candidate):
        candidate -= timedelta(days=1)

    return candidate


def get_latest_data_date(dataframe, label):

    if dataframe is None or dataframe.empty:
        raise ValueError(
            f"{label}: No market data available"
        )

    return dataframe.index[-1].date()


def keep_completed_sessions(dataframe, expected_session=None):
    """Discard rows later than the latest expected completed NSE session.

    Providers may include an in-progress daily candle for the current session.
    That candle is never used: callers must still validate that the last
    retained row is exactly the expected completed session.
    """
    if dataframe is None or dataframe.empty:
        return dataframe

    if expected_session is None:
        expected_session = get_latest_expected_nse_session()

    completed = [
        (stamp.to_pydatetime() if hasattr(stamp, "to_pydatetime") else stamp).date()
        <= expected_session
        for stamp in dataframe.index
    ]
    return dataframe.loc[completed].copy()


def validate_market_data_freshness(
    stock_df,
    benchmark_df,
    now=None
):
    """
    Require stock and benchmark data to end on the
    latest expected completed NSE trading session.

    Raises ValueError when either dataset is stale.
    """

    expected_date = get_latest_expected_nse_session(now)

    stock_date = get_latest_data_date(
        stock_df,
        "Stock"
    )

    benchmark_date = get_latest_data_date(
        benchmark_df,
        "Nifty 50 benchmark"
    )

    if stock_date != benchmark_date:
        raise ValueError(
            "DATA_DATE_MISMATCH: "
            f"Stock={stock_date}, "
            f"Benchmark={benchmark_date}, "
            f"Expected={expected_date}"
        )

    if stock_date != expected_date:
        raise ValueError(
            "STALE_DATA: "
            f"Stock and benchmark latest date={stock_date}, "
            f"Expected NSE session={expected_date}"
        )

    return {
        "status": "FRESH",
        "expected_date": str(expected_date),
        "stock_date": str(stock_date),
        "benchmark_date": str(benchmark_date),
    }


if __name__ == "__main__":

    now = datetime.now(IST)

    expected = get_latest_expected_nse_session(now)

    print("Current IST:", now)
    print("Expected latest completed NSE session:", expected)

    print(
        "Is 26 November a trading day:",
        is_nse_trading_day(date(2026, 11, 26))
    )

    print(
        "Is 24 November a trading day:",
        is_nse_trading_day(date(2026, 11, 24))
    )