
import time
import pandas as pd
import yfinance as yf

from pathlib import Path
from datetime import datetime


# ==========================================
# CONFIGURATION
# ==========================================

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

INPUT_FILE = DATA_DIR / "nifty500_symbols.csv"

MIN_PRICE = 100
MIN_AVG_TRADED_VALUE = 5 * 10_000_000  # ₹5 crore

LOOKBACK_SESSIONS = 20
DOWNLOAD_PERIOD = "3mo"

BATCH_SIZE = 20
INDIVIDUAL_RETRIES = 2

# Modes:
# "failed_retry" = test only the 14 previously failed stocks
# "full"         = scan the complete Nifty 500 universe

SCAN_MODE = "failed_retry"

FAILED_SYMBOLS = [
    "DEVYANI",
    "DUMMYHEG",
    "ELGIEQUIP",
    "GMRAIRPORT",
    "GICRE",
    "HBLENGINE",
    "HAVELLS",
    "HINDPETRO",
    "INDUSINDBK",
    "NAUKRI",
    "INOXWIND",
    "IPCALAB",
    "KSB",
    "NAM-INDIA",
]


# ==========================================
# OUTPUT FILES
# ==========================================

if SCAN_MODE == "failed_retry":

    OUTPUT_ALL = DATA_DIR / "universe_liquidity_retry_results.csv"
    OUTPUT_FILTERED = DATA_DIR / "filtered_universe_retry.csv"

else:

    OUTPUT_ALL = DATA_DIR / "universe_liquidity_results.csv"
    OUTPUT_FILTERED = DATA_DIR / "filtered_universe.csv"


# ==========================================
# BATCH DOWNLOAD
# ==========================================

def download_batch(symbols):

    tickers = [
        f"{symbol}.NS"
        for symbol in symbols
    ]

    print(
        f"\nDownloading batch of {len(tickers)} stocks..."
    )

    data = yf.download(
        tickers=tickers,
        period=DOWNLOAD_PERIOD,
        interval="1d",
        group_by="ticker",
        auto_adjust=False,
        threads=True,
        progress=False,
        timeout=60
    )

    if data is None or data.empty:
        raise ValueError(
            "Empty batch response from Yahoo Finance"
        )

    return data


# ==========================================
# EXTRACT STOCK FROM BATCH
# ==========================================

def extract_stock_frame(batch_data, symbol):

    ticker = f"{symbol}.NS"

    if isinstance(batch_data.columns, pd.MultiIndex):

        df = None

        for level in range(batch_data.columns.nlevels):

            level_values = (
                batch_data.columns
                .get_level_values(level)
            )

            if ticker in level_values:

                df = batch_data.xs(
                    ticker,
                    axis=1,
                    level=level
                )

                break

        if df is None:
            raise ValueError(
                f"{ticker} missing from batch response"
            )

    else:

        # Single-stock response fallback.
        df = batch_data.copy()

    df.columns = [
        str(column).strip()
        for column in df.columns
    ]

    required = {"Close", "Volume"}

    if not required.issubset(df.columns):

        raise ValueError(
            f"Close or Volume missing for {symbol}"
        )

    df = df.dropna(
        subset=["Close", "Volume"]
    ).copy()

    if len(df) < LOOKBACK_SESSIONS:

        raise ValueError(
            f"Only {len(df)} valid sessions available"
        )

    return df


# ==========================================
# INDIVIDUAL DOWNLOAD WITH RETRIES
# ==========================================

def download_individual_stock(symbol):

    ticker = f"{symbol}.NS"

    last_error = None

    for attempt in range(1, INDIVIDUAL_RETRIES + 1):

        try:

            print(
                f"Retrying individually: {ticker} "
                f"(attempt {attempt}/{INDIVIDUAL_RETRIES})"
            )

            df = yf.download(
                ticker,
                period=DOWNLOAD_PERIOD,
                interval="1d",
                auto_adjust=False,
                progress=False,
                threads=False,
                timeout=30
            )

            if df is None or df.empty:

                raise ValueError(
                    "Yahoo Finance returned empty data"
                )

            # Handle MultiIndex response.
            if isinstance(df.columns, pd.MultiIndex):

                df.columns = (
                    df.columns.get_level_values(0)
                )

            df.columns = [
                str(column).strip()
                for column in df.columns
            ]

            required = {"Close", "Volume"}

            if not required.issubset(df.columns):

                raise ValueError(
                    "Close or Volume columns missing"
                )

            df = df.dropna(
                subset=["Close", "Volume"]
            ).copy()

            if len(df) < LOOKBACK_SESSIONS:

                raise ValueError(
                    f"Only {len(df)} valid sessions available"
                )

            return df

        except Exception as error:

            last_error = error

            print(
                f"Individual download attempt failed: {error}"
            )

            if attempt < INDIVIDUAL_RETRIES:
                time.sleep(2)

    raise ValueError(
        f"Individual download failed after "
        f"{INDIVIDUAL_RETRIES} attempts: {last_error}"
    )


# ==========================================
# ANALYSE STOCK LIQUIDITY
# ==========================================

def analyse_stock(symbol, df):

    recent = df.tail(
        LOOKBACK_SESSIONS
    ).copy()

    recent["TradedValue"] = (
        recent["Close"] * recent["Volume"]
    )

    avg_traded_value = float(
        recent["TradedValue"].mean()
    )

    latest_price = float(
        recent["Close"].iloc[-1]
    )

    if (
        not pd.notna(avg_traded_value)
        or not pd.notna(latest_price)
        or latest_price <= 0
        or avg_traded_value < 0
    ):

        raise ValueError(
            "Invalid price or traded value"
        )

    price_pass = (
        latest_price > MIN_PRICE
    )

    liquidity_pass = (
        avg_traded_value > MIN_AVG_TRADED_VALUE
    )

    qualified = (
        price_pass and liquidity_pass
    )

    reasons = []

    if not price_pass:
        reasons.append("Price below threshold")

    if not liquidity_pass:
        reasons.append("Insufficient traded value")

    if qualified:
        reasons.append(
            "Passed price and liquidity filters"
        )

    return {
        "symbol": symbol,
        "latest_price": round(latest_price, 2),
        "avg_traded_value_20d": round(
            avg_traded_value, 2
        ),
        "avg_traded_value_crore": round(
            avg_traded_value / 10_000_000, 2
        ),
        "price_pass": price_pass,
        "liquidity_pass": liquidity_pass,
        "qualified": qualified,
        "reason": " | ".join(reasons),
        "error": "",
    }


# ==========================================
# ERROR RESULT
# ==========================================

def error_result(symbol, error):

    return {
        "symbol": symbol,
        "latest_price": None,
        "avg_traded_value_20d": None,
        "avg_traded_value_crore": None,
        "price_pass": False,
        "liquidity_pass": False,
        "qualified": False,
        "reason": "Data unavailable",
        "error": str(error),
    }


# ==========================================
# GET STOCK UNIVERSE
# ==========================================

def get_symbols():

    if SCAN_MODE == "failed_retry":

        print(
            "\nMODE: RETRY PREVIOUSLY FAILED STOCKS"
        )

        return FAILED_SYMBOLS.copy()

    if SCAN_MODE == "full":

        if not INPUT_FILE.exists():

            raise FileNotFoundError(
                f"Universe file not found: {INPUT_FILE}"
            )

        universe_df = pd.read_csv(
            INPUT_FILE
        )

        symbols = (
            universe_df["Symbol"]
            .dropna()
            .astype(str)
            .str.strip()
            .drop_duplicates()
            .tolist()
        )

        return symbols

    raise ValueError(
        f"Unsupported scan mode: {SCAN_MODE}"
    )


# ==========================================
# MAIN UNIVERSE FILTER
# ==========================================

def run_universe_filter():

    print("\n======================================")
    print("NSE UNIVERSE LIQUIDITY FILTER")
    print("======================================")

    symbols = get_symbols()

    print("Scan mode:", SCAN_MODE)
    print("Stocks to analyse:", len(symbols))
    print("Batch size:", BATCH_SIZE)
    print("Minimum price: ₹", MIN_PRICE)
    print("Minimum average traded value: ₹5 crore")

    results = []

    batches = [
        symbols[i:i + BATCH_SIZE]
        for i in range(
            0,
            len(symbols),
            BATCH_SIZE
        )
    ]

    processed = 0

    # ======================================
    # PROCESS BATCHES
    # ======================================

    for batch_number, batch_symbols in enumerate(
        batches,
        start=1
    ):

        print(
            f"\n========== BATCH "
            f"{batch_number}/{len(batches)} =========="
        )

        try:

            batch_data = download_batch(
                batch_symbols
            )

        except Exception as batch_error:

            print(
                "Batch download failed:",
                batch_error
            )

            print(
                "Using individual downloads for this batch."
            )

            batch_data = None

        # Process individual stocks.
        for symbol in batch_symbols:

            processed += 1

            print(
                f"\n[{processed}/{len(symbols)}] "
                f"Analysing {symbol}"
            )

            try:

                stock_df = None

                # First attempt: batch extraction.
                if batch_data is not None:

                    try:

                        stock_df = extract_stock_frame(
                            batch_data,
                            symbol
                        )

                    except Exception as batch_stock_error:

                        print(
                            "Batch extraction failed:",
                            batch_stock_error
                        )

                # Fallback: individual download.
                if stock_df is None:

                    stock_df = download_individual_stock(
                        symbol
                    )

                # Calculate liquidity.
                result = analyse_stock(
                    symbol,
                    stock_df
                )

                results.append(result)

                print(
                    f"Price: {result['latest_price']} | "
                    f"Avg traded value: "
                    f"₹{result['avg_traded_value_crore']} crore | "
                    f"Qualified: {result['qualified']}"
                )

            except Exception as error:

                print(
                    "Analysis failed:",
                    error
                )

                results.append(
                    error_result(
                        symbol,
                        error
                    )
                )

        if batch_number < len(batches):
            time.sleep(2)

    # ======================================
    # SAVE RESULTS
    # ======================================

    results_df = pd.DataFrame(results)

    DATA_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    results_df.to_csv(
        OUTPUT_ALL,
        index=False
    )

    filtered_df = results_df[
        results_df["qualified"] == True
    ].copy()

    filtered_df.to_csv(
        OUTPUT_FILTERED,
        index=False
    )

    # ======================================
    # SUMMARY
    # ======================================

    error_mask = (
        results_df["error"]
        .fillna("")
        .str.len() > 0
    )

    valid_results = results_df[
        ~error_mask
    ]

    qualified_count = int(
        results_df["qualified"].sum()
    )

    price_failures = int(
        (
            ~valid_results["price_pass"].astype(bool)
        ).sum()
    )

    liquidity_failures = int(
        (
            ~valid_results["liquidity_pass"].astype(bool)
        ).sum()
    )

    error_count = int(
        error_mask.sum()
    )

    print("\n======================================")
    print("LIQUIDITY FILTER SUMMARY")
    print("======================================")

    print("Stocks analysed:", len(results_df))
    print("Qualified stocks:", qualified_count)
    print("Price failures:", price_failures)
    print("Liquidity failures:", liquidity_failures)
    print("Data errors:", error_count)

    print("\nALL RESULTS:")
    print(OUTPUT_ALL)

    print("\nFILTERED UNIVERSE:")
    print(OUTPUT_FILTERED)

    if error_count:

        print("\nREMAINING DATA ERRORS:")

        print(
            results_df.loc[
                error_mask,
                ["symbol", "error"]
            ].to_string(index=False)
        )

    print(
        "\nCompleted:",
        datetime.now().isoformat(
            timespec="seconds"
        )
    )

    return results_df


# ==========================================
# EXECUTION
# ==========================================

if __name__ == "__main__":

    try:

        run_universe_filter()

    except Exception as error:

        print("\nUNIVERSE FILTER FAILED")
        print(error)

        raise