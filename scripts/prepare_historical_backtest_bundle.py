"""Prepare a sourced six-month Nifty 500 EQ research bundle.

Membership comes from NSE Indices' current constituent file, reversed through
the official 2026-09-30 broad-market review and amended for the 2026-07-17
merger replacement. Prices/actions are fetched from Yahoo Finance with raw
(non-dividend-adjusted) OHLC and action fields. Nifty 50 price and TRI are
queried from NSE Indices' historical-data endpoints.
"""

from __future__ import annotations

import json
import time
from datetime import date
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd
import requests
import yfinance as yf


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "backtest"
STOCKS_DIR = DATA_DIR / "stocks"
START = pd.Timestamp("2026-05-26")
END = pd.Timestamp("2026-11-26")
MEMBERSHIP_START = START - pd.Timedelta(days=5)
WARMUP_START = pd.Timestamp("2025-04-01")

CURRENT_CONSTITUENTS_URL = (
    "https://www.niftyindices.com/IndexConstituent/ind_nifty500list.csv"
)
SEPTEMBER_REVIEW_URL = (
    "https://www.niftyindices.com/Press_Release/ind_prs10082026.pdf"
)
JULY_MERGER_URL = (
    "https://www.niftyindices.com/Press_Release/ind_prs13072026_1.pdf"
)
VEDANTA_NOTICE_URLS = [
    "https://www.niftyindices.com/Press_Release/ind_prs17062026.pdf",
    "https://www.niftyindices.com/Press_Release/ind_prs19062026.pdf",
    "https://www.niftyindices.com/Press_Release/ind_prs22062026.pdf",
]
NIFTY_REPORTS_URL = "https://www.niftyindices.com/reports/historical-data"

# These are the 27 EQ exclusions and 23 EQ inclusions in the official Sep 2026
# Nifty 500 review. Four other inclusions in that notice are REIT units (RR).
SEPTEMBER_EXCLUDED = set("""
3MINDIA ABFRL ABLBL BAYERCROP BIKAJI BLUEDART BLUEJET BBTC MAPMYINDIA
CHALET DCMSHRIRAM ERIS GODIGIT INDGN JSWDULUX JUBLPHARMA LATENTVIEW
THELEELA NEWGEN NIVABUPA PFIZER SAPPHIRE SAREGAMA SBFC SONATSOFTW
SPLPETRO TRAVELFOOD
""".split())
SEPTEMBER_INCLUDED_EQ = set("""
AETHER AVANTIFEED AZAD BHARATCOAL BBOX CMPDI CLEANMAX CUPID FRACTAL
INOXINDIA KIRLOSBROS KSB MTARTECH PRIVISCL RUBICON SANSERA SHRIPISTON
STLTECH TDPOWERSYS THANGAMAYL VAML VISL VOGL VEDPOWER
""".split())

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/126 Safari/537.36",
    "Accept": "text/csv,application/json,*/*",
}


def _download_current_index_symbols() -> set[str]:
    response = requests.get(CURRENT_CONSTITUENTS_URL, headers=HEADERS, timeout=30)
    response.raise_for_status()
    frame = pd.read_csv(pd.io.common.BytesIO(response.content))
    if not {"Symbol", "Series"}.issubset(frame.columns):
        raise ValueError("Official Nifty 500 constituent file has unexpected columns")
    # Keep all index units here. NSE's current EQ/BE/RR series is not a
    # substitute for historical series; dated bhavcopies below determine EQ.
    current = set(frame["Symbol"].astype(str).str.strip().str.upper())
    if len(current) < 450:
        raise ValueError(f"Official constituent set is unexpectedly small: {len(current)}")
    if not (SEPTEMBER_INCLUDED_EQ - {"STLTECH"}).issubset(current):
        missing = (SEPTEMBER_INCLUDED_EQ - {"STLTECH"}) - current
        raise ValueError(f"Official current list does not reconcile September additions: {missing}")
    if SEPTEMBER_EXCLUDED & current:
        raise ValueError("Official current list still contains September exclusions")
    if "PFOCUS" not in current or "JBCHEPHARM" in current:
        raise ValueError("Official list does not reconcile the July merger replacement")
    return current


def _index_members_on(day: pd.Timestamp, current: set[str]) -> set[str]:
    members = set(current)
    if day < pd.Timestamp("2026-09-30"):
        members.difference_update(SEPTEMBER_INCLUDED_EQ)
        members.update(SEPTEMBER_EXCLUDED)
    if day < pd.Timestamp("2026-07-17"):
        members.discard("PFOCUS")
        members.add("JBCHEPHARM")
    return members


def _membership_history(current: set[str], reports: dict[pd.Timestamp, pd.DataFrame], dates) -> pd.DataFrame:
    """Reconstruct daily EQ membership from dated index changes and NSE series."""
    last_series: dict[str, str] = {}
    active_by_day = {}
    for day in dates:
        report = reports[day]
        # A missing report row can mean no trade; preserve the last official
        # series classification, while OHLCV validation still fails closed.
        last_series.update(dict(zip(report["SYMBOL"], report["SERIES"])))
        active_by_day[day] = {
            symbol for symbol in _index_members_on(day, current)
            if last_series.get(symbol) == "EQ"
        }
    rows = []
    symbols = set().union(*active_by_day.values()) if active_by_day else set()
    for symbol in sorted(symbols):
        active_dates = [day for day in dates if symbol in active_by_day[day]]
        if not active_dates:
            continue
        begin = previous = active_dates[0]
        intervals = []
        for day in active_dates[1:]:
            if dates.get_loc(day) != dates.get_loc(previous) + 1:
                intervals.append((begin, previous))
                begin = day
            previous = day
        intervals.append((begin, previous))
        for begin, finish in intervals:
            # Source URL identifies the official daily report used to validate
            # this dated EQ classification and the official index membership.
            source = ("https://nsearchives.nseindia.com/products/content/"
                      f"sec_bhavdata_full_{finish:%d%m%Y}.csv")
            rows.append({"symbol": symbol, "series": "EQ",
                         "valid_from": begin.date().isoformat(),
                         "valid_to": finish.date().isoformat(), "source_url": source})
    return pd.DataFrame(rows)


def _fetch_official_index(index_name: str, endpoint: str) -> pd.DataFrame:
    session = requests.Session()
    origin = "https://www.niftyindices.com"
    session.headers.update({
        **HEADERS, "Referer": NIFTY_REPORTS_URL, "Origin": origin,
        "Content-Type": "application/json; charset=utf-8",
    })
    cinfo = (
        "{'name':'NIFTY 50','startDate':'04/01/2025',"
        f"'endDate':'{END:%m/%d/%Y}','indexName':'Nifty 50'}}"
    )
    response = session.post(
        f"{origin}{endpoint}", json={"cinfo": cinfo}, timeout=60
    )
    response.raise_for_status()
    rows = response.json()
    if isinstance(rows, dict) and "d" in rows:
        rows = json.loads(rows["d"])
    if not isinstance(rows, list) or not rows:
        raise ValueError(f"Official Nifty 50 {index_name} response was empty")
    if index_name == "price":
        frame = pd.DataFrame(rows)
        frame["date"] = pd.to_datetime(frame["HistoricalDate"], format="%d %b %Y")
        frame["value"] = pd.to_numeric(frame["CLOSE"], errors="coerce")
    else:
        frame = pd.DataFrame(rows)
        frame["date"] = pd.to_datetime(frame["Date"], format="%d %b %Y")
        frame["value"] = pd.to_numeric(frame["TotalReturnsIndex"], errors="coerce")
    frame = frame.set_index("date")["value"].sort_index()
    frame = frame.loc[(frame.index >= WARMUP_START) & (frame.index <= END)]
    if frame.empty or frame.isna().any() or frame.le(0).any():
        raise ValueError(f"Official Nifty 50 {index_name} data is incomplete or invalid")
    return frame[~frame.index.duplicated(keep="last")]


def _extract_ticker(downloaded: pd.DataFrame, ticker: str, one_ticker: bool) -> pd.DataFrame:
    if downloaded is None or downloaded.empty:
        return pd.DataFrame()
    if not isinstance(downloaded.columns, pd.MultiIndex):
        return downloaded.copy() if one_ticker else pd.DataFrame()
    levels = [set(map(str, downloaded.columns.get_level_values(i))) for i in range(downloaded.columns.nlevels)]
    for level, values in enumerate(levels):
        if ticker in values:
            result = downloaded.xs(ticker, axis=1, level=level, drop_level=True)
            if isinstance(result.columns, pd.MultiIndex):
                result.columns = result.columns.get_level_values(-1)
            return result
    return pd.DataFrame()


def _download_yahoo_history(symbols: list[str]) -> dict[str, pd.DataFrame]:
    start_text = WARMUP_START.strftime("%Y-%m-%d")
    end_text = (END + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    output: dict[str, pd.DataFrame] = {}
    tickers = [f"{symbol}.NS" for symbol in symbols]
    for offset in range(0, len(tickers), 25):
        chunk = tickers[offset:offset + 25]
        downloaded = pd.DataFrame()
        for attempt in range(3):
            try:
                downloaded = yf.download(
                    chunk, start=start_text, end=end_text, interval="1d",
                    auto_adjust=False, actions=True, group_by="ticker",
                    threads=True, progress=False, timeout=45,
                )
                if not downloaded.empty:
                    break
            except Exception as error:
                print(f"Yahoo batch {offset // 25 + 1} attempt {attempt + 1}: {error}")
            if attempt < 2:
                time.sleep(2 ** attempt)
        for ticker in chunk:
            raw = _extract_ticker(downloaded, ticker, len(chunk) == 1)
            if raw.empty:
                continue
            raw.columns = [str(column).strip().title() for column in raw.columns]
            required = ["Open", "High", "Low", "Close", "Volume"]
            if not set(required).issubset(raw.columns):
                continue
            if "Dividends" not in raw.columns:
                # An absent action field is not proof of a complete zero-dividend series.
                continue
            if "Stock Splits" not in raw.columns:
                raw["Stock Splits"] = 0.0
            frame = raw[required + ["Dividends", "Stock Splits"]].copy()
            frame.index = pd.DatetimeIndex(pd.to_datetime(frame.index)).tz_localize(None).normalize()
            frame = frame.loc[~frame.index.duplicated(keep="last")].sort_index()
            for column in required + ["Dividends", "Stock Splits"]:
                frame[column] = pd.to_numeric(frame[column], errors="coerce")
            frame = frame.dropna(subset=required)
            frame["Dividends"] = frame["Dividends"].fillna(0.0)
            frame["Stock Splits"] = frame["Stock Splits"].fillna(0.0)
            frame = frame.loc[(frame.index >= WARMUP_START) & (frame.index <= END)]
            if not frame.empty:
                output[ticker[:-3].upper()] = frame
        done = min(offset + 25, len(tickers))
        print(f"Downloaded {done}/{len(tickers)} symbols; usable {len(output)}")
        time.sleep(0.5)

    missing = sorted(set(symbols) - set(output))
    # Retry missing symbols individually; this also handles unusual ticker names.
    for i, symbol in enumerate(missing, 1):
        ticker = f"{symbol}.NS"
        for attempt in range(3):
            try:
                raw = yf.download(
                    ticker, start=start_text, end=end_text, interval="1d",
                    auto_adjust=False, actions=True, progress=False, threads=False,
                    timeout=45,
                )
                frame = _extract_ticker(raw, ticker, True)
                frame.columns = [str(column).strip().title() for column in frame.columns]
                required = ["Open", "High", "Low", "Close", "Volume"]
                if frame.empty or not set(required + ["Dividends"]).issubset(frame.columns):
                    raise ValueError("no complete OHLCV/action response")
                if "Stock Splits" not in frame.columns:
                    frame["Stock Splits"] = 0.0
                frame = frame[required + ["Dividends", "Stock Splits"]].copy()
                frame.index = pd.DatetimeIndex(pd.to_datetime(frame.index)).tz_localize(None).normalize()
                for column in required + ["Dividends", "Stock Splits"]:
                    frame[column] = pd.to_numeric(frame[column], errors="coerce")
                frame = frame.dropna(subset=required)
                frame["Dividends"] = frame["Dividends"].fillna(0.0)
                frame["Stock Splits"] = frame["Stock Splits"].fillna(0.0)
                frame = frame.loc[(frame.index >= WARMUP_START) & (frame.index <= END)]
                if not frame.empty:
                    output[symbol] = frame
                    break
            except Exception as error:
                if attempt == 2:
                    print(f"No Yahoo history for {symbol}: {error}")
                else:
                    time.sleep(2 ** attempt)
        if i % 25 == 0:
            print(f"Retried {i}/{len(missing)} missing symbols; usable {len(output)}")
    return output


def _fetch_nse_bhavcopy(day: pd.Timestamp) -> tuple[pd.Timestamp, pd.DataFrame]:
    cache_dir = ROOT / "data" / "backtest_nse_source_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"sec_bhavdata_full_{day:%d%m%Y}.csv"
    if path.exists():
        content = path.read_bytes()
    else:
        url = (
            "https://nsearchives.nseindia.com/products/content/"
            f"sec_bhavdata_full_{day:%d%m%Y}.csv"
        )
        response = requests.get(url, headers=HEADERS, timeout=45)
        response.raise_for_status()
        content = response.content
        if not content or content.lstrip().startswith(b"<"):
            raise ValueError(f"NSE response is not a CSV for {day.date()}")
        path.write_bytes(content)
    frame = pd.read_csv(pd.io.common.BytesIO(content))
    frame.columns = [str(column).strip() for column in frame.columns]
    required = {
        "SYMBOL", "SERIES", "DATE1", "OPEN_PRICE", "HIGH_PRICE",
        "LOW_PRICE", "CLOSE_PRICE", "TTL_TRD_QNTY",
    }
    if not required.issubset(frame.columns):
        raise ValueError(f"NSE bhavcopy {day.date()} lacks required columns")
    frame["SYMBOL"] = frame["SYMBOL"].astype(str).str.strip().str.upper()
    frame["SERIES"] = frame["SERIES"].astype(str).str.strip().str.upper()
    frame["_DATE"] = pd.to_datetime(
        frame["DATE1"].astype(str).str.strip(), format="%d-%b-%Y", errors="coerce"
    ).dt.normalize()
    if not frame["_DATE"].eq(day.normalize()).any():
        raise ValueError(f"NSE bhavcopy date does not match {day.date()}")
    return day.normalize(), frame


def _fetch_session_reports(benchmark_dates: pd.DatetimeIndex):
    first = max(0, benchmark_dates.searchsorted(START) - 1)
    dates = pd.DatetimeIndex(benchmark_dates[first:benchmark_dates.searchsorted(END, side="right")])
    reports = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(_fetch_nse_bhavcopy, day): day for day in dates}
        for future in as_completed(futures):
            day, frame = future.result()
            reports[day] = frame
            print(f"Fetched official NSE series report {len(reports)}/{len(dates)}")
    return dates, reports


def _reconstruct_jb_pharma_from_nse(benchmark_dates: pd.DatetimeIndex) -> pd.DataFrame:
    """Recover merger-delisted history from NSE daily files when Yahoo omits it."""
    start_location = benchmark_dates.searchsorted(START)
    needed = pd.DatetimeIndex(benchmark_dates[max(0, start_location - 253):
                                               benchmark_dates.searchsorted("2026-07-17")])
    rows = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(_fetch_nse_bhavcopy, day): day for day in needed}
        for i, future in enumerate(as_completed(futures), 1):
            day, report = future.result()
            matches = report.loc[report["SYMBOL"].eq("JBCHEPHARM") & report["SERIES"].eq("EQ")]
            if matches.empty:
                raise ValueError(f"NSE has no JBCHEPHARM EQ bar for required warm-up/session {day.date()}")
            row = matches.iloc[-1]
            rows.append({"Date": day, "Open": row["OPEN_PRICE"], "High": row["HIGH_PRICE"],
                         "Low": row["LOW_PRICE"], "Close": row["CLOSE_PRICE"],
                         "Volume": row["TTL_TRD_QNTY"]})
            if i % 50 == 0:
                print(f"Reconstructed JBCHEPHARM from NSE {i}/{len(needed)} sessions")
    frame = pd.DataFrame(rows).set_index("Date").sort_index()
    frame["Dividends"] = 0.0
    # NSE corporate action filing lists the 2026-05-29 ex-date ₹9.30 dividend.
    if pd.Timestamp("2026-05-29") in frame.index:
        frame.loc[pd.Timestamp("2026-05-29"), "Dividends"] = 9.30
    frame["Stock Splits"] = 0.0
    return frame


def _apply_official_execution_bars(
    stock_data: dict[str, pd.DataFrame],
    history: pd.DataFrame,
    benchmark_dates: pd.DatetimeIndex,
    reports: dict[pd.Timestamp, pd.DataFrame] | None = None,
) -> dict[str, int]:
    if reports is None:
        dates, reports = _fetch_session_reports(benchmark_dates)
    else:
        dates = pd.DatetimeIndex(sorted(reports))
    results = {}
    for day, all_series in reports.items():
        frame = all_series.loc[all_series["SERIES"].eq("EQ")].copy()
        if frame.duplicated(["SYMBOL"]).any():
            dupes = frame.loc[frame.duplicated(["SYMBOL"], keep=False), "SYMBOL"].unique()
            raise ValueError(f"NSE has duplicate EQ bars on {day.date()}: {dupes[:5]}")
        results[day] = frame.set_index("SYMBOL")

    def active_on(day: pd.Timestamp) -> set[str]:
        start = pd.to_datetime(history["valid_from"])
        end = pd.to_datetime(history["valid_to"], errors="coerce")
        mask = (start <= day) & (end.isna() | (end >= day))
        return set(history.loc[mask, "symbol"].astype(str))

    counts = {"official_bars": 0, "nse_missing_rows": 0}
    price_cols = ["Open", "High", "Low", "Close"]
    for day in dates:
        report = results[day]
        members = active_on(day)
        for symbol in members:
            frame = stock_data[symbol]
            if symbol not in report.index:
                # NSE omits securities that did not trade. Keep Yahoo's row only
                # when it independently reports zero volume; never use a vendor
                # candle with claimed turnover where the official report has none.
                if day not in frame.index:
                    raise ValueError(f"MISSING_HISTORY: {symbol} absent from Yahoo and NSE on {day.date()}")
                if float(frame.loc[day, "Volume"]) > 0:
                    raise ValueError(f"DATA_MISMATCH: Yahoo reports trades but NSE does not for {symbol} on {day.date()}")
                counts["nse_missing_rows"] += 1
                continue
            row = report.loc[symbol]
            raw_close = float(row["CLOSE_PRICE"])
            if raw_close <= 0:
                raise ValueError(f"NSE has non-positive close for {symbol} on {day.date()}")
            split_events = frame.loc[
                (frame.index > day) & frame["Stock Splits"].fillna(0).ne(0), "Stock Splits"
            ]
            future_split_factor = float(split_events.prod()) if len(split_events) else 1.0
            price_factor = 1.0 / future_split_factor
            if day in frame.index:
                vendor_close = float(frame.loc[day, "Close"])
                observed_factor = vendor_close / raw_close
                if abs(observed_factor / price_factor - 1.0) > 0.02:
                    raise ValueError(
                        f"SPLIT_ADJUSTMENT_MISMATCH: {symbol} on {day.date()} "
                        f"official={raw_close}, vendor={vendor_close}, expected_factor={price_factor}"
                    )
            for col, source_col in zip(price_cols, ["OPEN_PRICE", "HIGH_PRICE", "LOW_PRICE", "CLOSE_PRICE"]):
                frame.loc[day, col] = float(row[source_col]) * price_factor
            frame.loc[day, "Volume"] = float(row["TTL_TRD_QNTY"]) / price_factor
            counts["official_bars"] += 1

    for frame in stock_data.values():
        frame["Dividends"] = frame["Dividends"].fillna(0.0)
    return counts


def _patch_benchmark_session_gaps(stock_data, history, benchmark_dates):
    """Fill benchmark-aligned Yahoo gaps from NSE, including special sessions."""
    start_location = benchmark_dates.searchsorted(START)
    warmup = benchmark_dates[max(0, start_location - 253):start_location]
    if len(warmup) < 253:
        raise ValueError("Insufficient benchmark warm-up dates for stock-gap reconciliation")
    replay_dates = benchmark_dates[start_location:benchmark_dates.searchsorted(END, side="right")]
    active = set()
    starts = pd.to_datetime(history["valid_from"])
    ends = pd.to_datetime(history["valid_to"], errors="coerce")
    for day in replay_dates:
        active.update(history.loc[(starts <= day) & (ends.isna() | (ends >= day)), "symbol"])
    missing_dates = set()
    for symbol in active:
        frame = stock_data[symbol]
        if frame.index.empty or warmup[0] < frame.index[0]:
            continue  # newly listed; the strategy intentionally waits for 253 bars
        missing_dates.update(warmup.difference(frame.index))
    patched = 0
    for day in sorted(missing_dates):
        _, all_series = _fetch_nse_bhavcopy(day)
        report = all_series.loc[all_series["SERIES"].eq("EQ")].set_index("SYMBOL")
        for symbol in active:
            frame = stock_data[symbol]
            if day in frame.index:
                continue
            if frame.index.empty or day < frame.index[0]:
                continue
            if symbol not in report.index:
                # NSE's full bhavcopy contains only traded securities. On a
                # verified special session, represent a non-traded member as
                # a flat zero-volume bar; never carry forward a traded price.
                prior = frame.loc[frame.index < day]
                if prior.empty:
                    raise ValueError(f"No prior close to represent non-trading {symbol} on {day.date()}")
                close = float(prior.iloc[-1]["Close"])
                frame.loc[day, ["Open", "High", "Low", "Close"]] = close
                frame.loc[day, "Volume"] = 0.0
                frame.loc[day, "Dividends"] = 0.0
                frame.loc[day, "Stock Splits"] = 0.0
                patched += 1
                continue
            row = report.loc[symbol]
            future_splits = frame.loc[(frame.index > day) & frame["Stock Splits"].ne(0), "Stock Splits"]
            factor = 1.0 / float(future_splits.prod()) if len(future_splits) else 1.0
            frame.loc[day, ["Open", "High", "Low", "Close"]] = [
                float(row[c]) * factor for c in ("OPEN_PRICE", "HIGH_PRICE", "LOW_PRICE", "CLOSE_PRICE")
            ]
            frame.loc[day, "Volume"] = float(row["TTL_TRD_QNTY"]) / factor
            frame.loc[day, "Dividends"] = 0.0
            frame.loc[day, "Stock Splits"] = 0.0
            patched += 1
    return {"dates": len(missing_dates), "bars": patched}


def main() -> None:
    if DATA_DIR.exists() and any(DATA_DIR.iterdir()):
        raise FileExistsError(
            f"Refusing to overwrite existing backtest inputs in {DATA_DIR}"
        )
    current = _download_current_index_symbols()
    benchmark_price = _fetch_official_index(
        "price", "/BackPage/getHistoricaldatatabletoString"
    )
    benchmark_tri = _fetch_official_index(
        "tri", "/BackPage/getTotalReturnIndexString"
    )
    common = benchmark_price.index.intersection(benchmark_tri.index)
    benchmark_price = benchmark_price.loc[common]
    benchmark_tri = benchmark_tri.loc[common]
    if not benchmark_price.index.equals(benchmark_tri.index):
        raise ValueError("Official Nifty 50 price/TRI session dates do not match")
    if len(benchmark_price.loc[benchmark_price.index < START]) < 253:
        raise ValueError("Official benchmark does not provide 253 warm-up sessions")
    if END not in benchmark_price.index:
        raise ValueError(f"Official Nifty 50 benchmark has no completed {END.date()} session")

    session_dates, reports = _fetch_session_reports(benchmark_price.index)
    history = _membership_history(current, reports, session_dates)
    if history.empty:
        raise ValueError("No historical Nifty 500 EQ membership could be reconstructed")
    active_symbols = sorted(set(history["symbol"]))
    print(
        f"Historical EQ membership: {len(active_symbols)} unique symbols; "
        f"{len(current)} current index constituents; {len(history)} dated EQ intervals"
    )

    stock_data = _download_yahoo_history(active_symbols)
    if "JBCHEPHARM" not in stock_data:
        stock_data["JBCHEPHARM"] = _reconstruct_jb_pharma_from_nse(benchmark_price.index)
    missing = sorted(set(active_symbols) - set(stock_data))
    if missing:
        raise ValueError(
            "Historical OHLCV/dividend history is missing for active members; "
            f"bundle not written. Symbols: {', '.join(missing[:35])}"
        )
    warmup_patch = _patch_benchmark_session_gaps(
        stock_data, history, benchmark_price.index
    )
    official_bar_counts = _apply_official_execution_bars(
        stock_data, history, benchmark_price.index, reports=reports
    )

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    STOCKS_DIR.mkdir(parents=True, exist_ok=True)
    history.to_csv(DATA_DIR / "universe_history.csv", index=False)
    pd.DataFrame({"Close": benchmark_price}).to_csv(DATA_DIR / "nifty50_price.csv")
    pd.DataFrame({"Total Return Index": benchmark_tri}).to_csv(DATA_DIR / "nifty50_tri.csv")
    for symbol, frame in stock_data.items():
        frame.to_csv(STOCKS_DIR / f"{symbol}.csv", index=True)

    manifest = {
        "complete_point_in_time_history": True,
        "coverage_start": WARMUP_START.date().isoformat(),
        "coverage_end": END.date().isoformat(),
        "performance_start": START.date().isoformat(),
        "performance_end": END.date().isoformat(),
        "universe_scope": "Nifty 500 constituents in NSE EQ series; non-EQ units and demerger placeholder symbols excluded",
        "source_url": CURRENT_CONSTITUENTS_URL,
        "membership_sources": [
            CURRENT_CONSTITUENTS_URL, SEPTEMBER_REVIEW_URL, JULY_MERGER_URL,
            *VEDANTA_NOTICE_URLS,
        ],
        "corporate_action_sources": [
            "https://www.nseindia.com/companies-listing/corporate-filings-actions?symbol=JBCHEPHARM"
        ],
        "session_calendar_sources": [
            "https://nsearchives.nseindia.com/content/circulars/CMTR72349.pdf"
        ],
        "stock_price_source": "Yahoo Finance historical chart; auto_adjust=False, actions=True; dividend and split action fields retained",
        "execution_bar_source": "NSE official sec_bhavdata_full EQ rows for historical signal/fill/mark sessions; OHLC scaled to split-adjusted Yahoo share basis",
        "benchmark_source": NIFTY_REPORTS_URL,
        "benchmark_end_session": END.date().isoformat(),
        "replay_start_session": START.date().isoformat(),
        "notes": [
            "September Nifty 500 review reversed from official current constituent list; four added REIT units excluded because they are not NSE EQ series.",
            "July 17, 2026 JBCHEPHARM/PFOCUS merger replacement applied.",
            "Temporary Vedanta demerger dummy symbols are not tradable NSE EQ securities and are excluded from the trading universe.",
            "Research window is six months; this is exploratory evidence, not a profitability guarantee.",
            f"Official NSE session bars applied: {official_bar_counts['official_bars']}; NSE omitted rows: {official_bar_counts['nse_missing_rows']}.",
            f"NSE special-session warm-up gaps patched: {warmup_patch['bars']} bars across {warmup_patch['dates']} sessions; absent EQ rows are explicit flat zero-volume no-trade bars.",
        ],
    }
    (DATA_DIR / "universe_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    print(
        f"Bundle saved: {len(stock_data)} stocks, {len(benchmark_price)} benchmark "
        f"sessions, {len(history)} membership intervals"
    )


if __name__ == "__main__":
    main()
