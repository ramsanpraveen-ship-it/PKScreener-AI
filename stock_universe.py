
import pandas as pd
import requests

from io import StringIO
from pathlib import Path
from datetime import datetime


# ==========================================
# CONFIGURATION
# ==========================================

INDEX_URLS = [
    "https://nsearchives.nseindia.com/content/indices/ind_nifty500list.csv",
    "https://www.niftyindices.com/IndexConstituent/ind_nifty500list.csv",
]

PROJECT_DIR = Path(__file__).resolve().parent
DATA_DIR = PROJECT_DIR / "data"

RAW_FILE = DATA_DIR / "nifty500_constituents_raw.csv"
OUTPUT_FILE = DATA_DIR / "nifty500_symbols.csv"


# ==========================================
# DOWNLOAD CONSTITUENTS
# ==========================================

def download_constituents():

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 Chrome/130.0.0.0 Safari/537.36"
        ),
        "Accept": "text/csv,text/plain,*/*",
        "Referer": "https://www.niftyindices.com/",
    }

    for url in INDEX_URLS:

        try:
            print(f"Trying source: {url}")

            response = requests.get(
                url,
                headers=headers,
                timeout=30
            )

            response.raise_for_status()

            if not response.text.strip():
                raise ValueError("Empty CSV response")

            # Save the original downloaded CSV.
            DATA_DIR.mkdir(parents=True, exist_ok=True)

            RAW_FILE.write_text(
                response.text,
                encoding="utf-8"
            )

            print("Constituent CSV downloaded successfully.")

            return response.text

        except Exception as error:
            print(f"Source failed: {error}")

    raise RuntimeError(
        "Unable to download Nifty 500 constituents "
        "from the available official sources."
    )


# ==========================================
# PROCESS CONSTITUENTS
# ==========================================

def process_constituents(csv_text):

    df = pd.read_csv(
        StringIO(csv_text),
        encoding="utf-8-sig"
    )

    # Normalize column names.
    df.columns = [
        str(column).strip().lower()
        for column in df.columns
    ]

    required_columns = {"symbol", "series"}

    missing = required_columns - set(df.columns)

    if missing:
        raise ValueError(
            f"Required CSV columns missing: {missing}. "
            f"Available columns: {list(df.columns)}"
        )

    df["symbol"] = df["symbol"].astype("string").str.strip()
    df["series"] = df["series"].astype("string").str.strip().str.upper()

    original_count = len(df)

    # Keep only regular NSE equity series.
    equity_df = df[
        (df["series"] == "EQ")
        & df["symbol"].notna()
        & (df["symbol"] != "")
    ].copy()

    # Remove duplicate symbols.
    equity_df = equity_df.drop_duplicates(
        subset=["symbol"]
    )

    symbols = sorted(
        equity_df["symbol"].tolist()
    )

    if not symbols:
        raise ValueError(
            "No valid EQ symbols found in the constituent CSV."
        )

    print("\nCONSTITUENT PROCESSING")
    print("--------------------------------------")
    print("Total CSV rows:", original_count)
    print("Regular EQ constituents:", len(symbols))
    print("Unique symbols:", len(set(symbols)))

    return equity_df, symbols


# ==========================================
# SAVE UNIVERSE
# ==========================================

def save_universe(equity_df):

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    output_df = equity_df[
        ["symbol", "series"]
    ].copy()

    output_df = output_df.rename(
        columns={
            "symbol": "Symbol",
            "series": "Series",
        }
    )

    output_df.to_csv(
        OUTPUT_FILE,
        index=False
    )

    print("\nUniverse saved:", OUTPUT_FILE)

    return OUTPUT_FILE


# ==========================================
# MAIN UNIVERSE FUNCTION
# ==========================================

def get_nifty500_universe():

    print("\n======================================")
    print("NIFTY 500 STOCK UNIVERSE")
    print("======================================")

    csv_text = download_constituents()

    equity_df, symbols = process_constituents(
        csv_text
    )

    save_universe(equity_df)

    print("\nSAMPLE SYMBOLS")
    print("--------------------------------------")

    for symbol in symbols[:20]:
        print(symbol)

    print("\nTotal symbols available:", len(symbols))
    print("Generated at:", datetime.now().isoformat(timespec="seconds"))

    return symbols


# ==========================================
# MAIN
# ==========================================

if __name__ == "__main__":

    try:
        get_nifty500_universe()

    except Exception as error:
        print("\nUNIVERSE DOWNLOAD FAILED")
        print(error)