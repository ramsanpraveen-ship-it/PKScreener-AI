
import pandas as pd
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "data"

ORIGINAL_FILE = DATA_DIR / "universe_liquidity_results.csv"
RETRY_FILE = DATA_DIR / "universe_liquidity_retry_results.csv"

OUTPUT_ALL = DATA_DIR / "universe_liquidity_final.csv"
OUTPUT_FILTERED = DATA_DIR / "filtered_universe_final.csv"


def main():

    original = pd.read_csv(ORIGINAL_FILE)
    retry = pd.read_csv(RETRY_FILE)

    if original["symbol"].duplicated().any():
        raise ValueError("Duplicate symbols in original results")

    if retry["symbol"].duplicated().any():
        raise ValueError("Duplicate symbols in retry results")

    original = original.set_index("symbol")
    retry = retry.set_index("symbol")

    unknown_symbols = retry.index.difference(original.index)

    if len(unknown_symbols):
        raise ValueError(
            f"Retry contains unknown symbols: {list(unknown_symbols)}"
        )

    # Replace original results for retried symbols.
    for column in retry.columns:
        original.loc[retry.index, column] = retry[column]

    final = original.reset_index()

    if len(final) != len(original):
        raise ValueError("Unexpected row count after merging")

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    final.to_csv(OUTPUT_ALL, index=False)

    # Only stocks passing both filters.
    filtered = final[
        final["qualified"].fillna(False).astype(bool)
    ].copy()

    filtered.to_csv(OUTPUT_FILTERED, index=False)

    # Calculate summary.
    errors = (
        final["error"].fillna("").str.strip() != ""
    )

    valid = final[~errors]

    price_failures = (
        ~valid["price_pass"].fillna(False).astype(bool)
    ).sum()

    liquidity_failures = (
        ~valid["liquidity_pass"].fillna(False).astype(bool)
    ).sum()

    print("\n======================================")
    print("FINAL NSE UNIVERSE SUMMARY")
    print("======================================")

    print("Total constituents:", len(final))
    print("Qualified:", len(filtered))
    print("Price failures:", int(price_failures))
    print("Liquidity failures:", int(liquidity_failures))
    print("Data errors:", int(errors.sum()))

    print("\nRemaining errors:")

    print(
        final.loc[errors, ["symbol", "error"]]
        .to_string(index=False)
    )

    print("\nSaved files:")
    print(OUTPUT_ALL)
    print(OUTPUT_FILTERED)


if __name__ == "__main__":
    main()