"""Download and inventory the candidate Kaggle OHLCV bundle; not a validation certificate."""
from pathlib import Path
import hashlib
import os
import pandas as pd


DATASET = "shreyashautomation/nifty500-companies-5-years-stock-market-data"


def main():
    try:
        import kagglehub
    except ImportError as exc:
        raise SystemExit("Install optional kagglehub first: python -m pip install kagglehub") from exc
    cache_root = Path(os.environ.get("KAGGLEHUB_CACHE", "~/.cache/kagglehub")).expanduser()
    versions = cache_root / "datasets" / DATASET / "versions"
    cached_versions = sorted((item for item in versions.iterdir() if item.is_dir()),
                             key=lambda item: int(item.name) if item.name.isdigit() else -1) if versions.is_dir() else []
    if cached_versions:
        path = cached_versions[-1]
    else:
        path = Path(kagglehub.dataset_download(DATASET))
    print(f"Dataset directory: {path}")
    for item in sorted(path.rglob("*")):
        if item.is_file():
            print(f"{item.relative_to(path)}\t{item.stat().st_size} bytes")
            if item.suffix.lower() != ".csv":
                continue
            frame = pd.read_csv(item)
            date_col = next((c for c in frame if c.lower() in {"date", "datetime", "timestamp"}), None)
            symbol_col = next((c for c in frame if c.lower() in {"symbol", "ticker", "tradingsymbol", "stock"}), None)
            date = pd.to_datetime(frame[date_col], errors="coerce") if date_col else None
            prices = [c for c in ("Open", "High", "Low", "Close") if c in frame]
            invalid_ohlc = 0
            if len(prices) == 4:
                invalid_ohlc = int(((frame["High"] + 1e-6 < frame[["Open", "Close", "Low"]].max(axis=1))
                                    | (frame["Low"] - 1e-6 > frame[["Open", "Close", "High"]].min(axis=1))).sum())
            print(f"  rows={len(frame)} columns={list(frame.columns)}")
            print(f"  date_range={date.min()}..{date.max()} invalid_dates={int(date.isna().sum()) if date is not None else 'unknown'}")
            print(f"  unique_symbols={int(frame[symbol_col].nunique()) if symbol_col else 'unknown'}")
            print(f"  duplicate_rows={int(frame.duplicated().sum())} invalid_ohlc={invalid_ohlc}")
            if "Volume" in frame:
                print(f"  zero_volume_rows={int(frame['Volume'].eq(0).sum())}")
            print(f"  nulls={frame.isna().sum().to_dict()}")
            print(f"  sha256={hashlib.sha256(item.read_bytes()).hexdigest()}")
    print("Inventory only: validate schema, date coverage, corporate actions, constituent membership, and benchmark provenance before backtesting.")


if __name__ == "__main__":
    main()
