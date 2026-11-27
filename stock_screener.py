
import csv
import json
from datetime import datetime
from pathlib import Path
import time

from technical_engine import run_technical_analysis
from relative_strength import fetch_close_prices, INDEX_SYMBOL
from risk_manager import MAX_RISK_PER_TRADE, MAX_POSITION_VALUE
from nse_calendar import (
    get_latest_expected_nse_session,
    get_latest_data_date,
)


# ==========================================
# CONFIGURATION
# ==========================================

DEFAULT_PERIOD = "2y"

PROJECT_DIR = Path(__file__).resolve().parent

UNIVERSE_FILE = (
    PROJECT_DIR / "data" / "filtered_universe_final.csv"
)

OUTPUT_DIR = PROJECT_DIR / "data" / "screening_results"

# First test: scan only 10 stocks.
# Later increase to 50 and then None for all stocks.
SCAN_LIMIT = None


# ==========================================
# LOAD STOCK UNIVERSE
# ==========================================

def load_universe(csv_file=UNIVERSE_FILE):

    if not csv_file.exists():
        raise FileNotFoundError(
            f"Universe file not found: {csv_file}"
        )

    symbols = []
    seen = set()

    with open(
        csv_file,
        mode="r",
        newline="",
        encoding="utf-8-sig"
    ) as file:

        reader = csv.DictReader(file)

        if not reader.fieldnames:
            raise ValueError("Universe CSV has no header")

        symbol_column = next(
            (
                column
                for column in reader.fieldnames
                if column.strip().lower() == "symbol"
            ),
            None
        )

        if symbol_column is None:
            raise ValueError(
                "CSV must contain a 'symbol' column"
            )

        for row in reader:

            symbol = (row.get(symbol_column) or "").strip().upper()

            if not symbol:
                continue

            qualified = str(
                row.get("qualified", "true")
            ).strip().lower()

            if qualified not in ("true", "1", "yes"):
                continue

            if symbol not in seen:
                symbols.append(symbol)
                seen.add(symbol)

    if not symbols:
        raise ValueError(
            "No qualified stock symbols found in universe CSV"
        )

    return symbols


# ==========================================
# REJECTION REASONS
# ==========================================

def explain_decision(result):

    summary = result.get("screening_summary", {})
    breakout = result.get("breakout_analysis", {})

    if summary.get("candidate_status") == "INSUFFICIENT_HISTORY":
        info = result.get("data_info", {})
        available = info.get("aligned_sessions", 0)
        return [f"Only {available} aligned sessions; 253 are required by the current rules"]

    reasons = []

    if not summary.get("trend_template_pass", False):
        reasons.append(
            "Trend template conditions not satisfied"
        )

    if not summary.get("relative_strength_pass", False):
        reasons.append(
            "Relative strength conditions not satisfied"
        )

    if not summary.get("vcp_sequence_pass", False):
        reasons.append(
            "VCP contraction sequence not satisfied"
        )

    if not summary.get("breakout_confirmed", False):

        breakout_status = breakout.get(
            "status", "UNKNOWN"
        )

        breakout_reasons = {
            "BELOW_PIVOT":
                "Price is below the breakout pivot",

            "ABOVE_PIVOT_NOT_FRESH":
                "Price is above pivot but no fresh breakout",

            "UNCONFIRMED_LOW_VOLUME":
                "Breakout volume confirmation failed",

            "UNCONFIRMED_WEAK_CLOSE":
                "Breakout candle closing strength is insufficient",

            "OVEREXTENDED":
                "Price is too extended above the pivot",

            "UNKNOWN":
                "Breakout confirmation unavailable",
        }

        reasons.append(
            breakout_reasons.get(
                breakout_status,
                f"Breakout not confirmed: {breakout_status}"
            )
        )

    if not reasons:
        reasons.append(
            "No rejection reason identified by current screening rules"
        )

    return reasons


# ==========================================
# RESULT EXTRACTION
# ==========================================

def extract_screening_row(result):

    trend = result.get("trend_analysis", {})
    relative_strength = result.get(
        "relative_strength_analysis", {}
    )
    breakout = result.get("breakout_analysis", {})
    summary = result.get("screening_summary", {})
    levels = result.get("entry_exit_analysis", {})
    entry = levels.get("entry_price")
    stop = levels.get("stop_loss")
    target = levels.get("target_reference_2r")
    trend_count = trend.get("conditions_passed") or 0
    confidence = round((float(trend_count) / 9 * 50) + (20 if summary.get("relative_strength_pass") else 0) + (15 if summary.get("vcp_sequence_pass") else 0) + (15 if summary.get("breakout_confirmed") else 0), 1)
    quantity = 0
    try:
        risk_per_share = float(entry) - float(stop)
        if risk_per_share > 0 and float(entry) > 0:
            quantity = min(int(MAX_RISK_PER_TRADE // risk_per_share), int(MAX_POSITION_VALUE // float(entry)))
    except (TypeError, ValueError):
        pass

    rejection_reasons = explain_decision(result)

    return {
        "analysis_date": result.get("analysis_date"),
        "symbol": result.get("symbol"),
        "latest_price": result.get("latest_price"),
        "entry_reference": entry,
        "stop_loss": stop,
        "target_price": target,
        "breakout_level": breakout.get("breakout_level"),
        "planned_quantity": quantity,
        "confidence_pct": confidence,
        "eligible_for_paper": bool(summary.get("candidate_status") == "BREAKOUT_CONFIRMED" and quantity > 0),
        "market_data_source": result.get("data_info", {}).get("latest_bar_source"),

        "candidate_status": summary.get("candidate_status"),

        "trend_conditions_passed":
            trend.get("conditions_passed"),

        "trend_template_pass":
            summary.get("trend_template_pass"),

        "relative_strength":
            relative_strength.get(
                "weighted_relative_performance"
            ),

        "relative_strength_pass":
            summary.get("relative_strength_pass"),

        "vcp_sequence_pass":
            summary.get("vcp_sequence_pass"),

        "breakout_status":
            breakout.get("status"),

        "breakout_confirmed":
            summary.get("breakout_confirmed"),

        "rejection_reasons":
            " | ".join(rejection_reasons),

        "error": "",
        "rank": "",
    }


# ==========================================
# RANKING
# ==========================================

def rank_results(results):

    status_priority = {
        "BREAKOUT_CONFIRMED": 0,
        "SETUP_WATCH": 1,
        "NOT_QUALIFIED": 2,
        "INSUFFICIENT_HISTORY": 3,
        "ERROR": 4,
    }

    def numeric_value(value, default=-999999):

        try:
            number = float(value)

            if number != number:
                return default

            return number

        except (TypeError, ValueError):
            return default

    results.sort(
        key=lambda row: (
            status_priority.get(
                row.get("candidate_status"), 4
            ),
            -numeric_value(
                row.get("relative_strength")
            ),
            -numeric_value(
                row.get("trend_conditions_passed"), 0
            ),
        )
    )

    rank = 0

    for row in results:

        if row.get("candidate_status") == "BREAKOUT_CONFIRMED":
            rank += 1
            row["rank"] = rank
        else:
            row["rank"] = ""

    return results


# ==========================================
# CSV EXPORT
# ==========================================

def save_results(results):

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    timestamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    fieldnames = [
        "rank",
        "analysis_date",
        "symbol",
        "latest_price",
        "entry_reference",
        "stop_loss",
        "target_price",
        "breakout_level",
        "planned_quantity",
        "confidence_pct",
        "eligible_for_paper",
        "market_data_source",
        "candidate_status",
        "trend_conditions_passed",
        "trend_template_pass",
        "relative_strength",
        "relative_strength_pass",
        "vcp_sequence_pass",
        "breakout_status",
        "breakout_confirmed",
        "rejection_reasons",
        "error",
    ]

    # Complete screening results.
    all_file = OUTPUT_DIR / (
        f"screening_results_{timestamp}.csv"
    )

    with open(
        all_file,
        mode="w",
        newline="",
        encoding="utf-8"
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames
        )

        writer.writeheader()
        writer.writerows(results)

    # Only confirmed breakout candidates.
    candidates = [
        row for row in results
        if row.get("candidate_status") == "BREAKOUT_CONFIRMED"
    ]

    candidate_file = OUTPUT_DIR / (
        f"breakout_candidates_{timestamp}.csv"
    )

    with open(
        candidate_file,
        mode="w",
        newline="",
        encoding="utf-8"
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames
        )

        writer.writeheader()
        writer.writerows(candidates)

    return all_file, candidate_file


def save_scan_metadata(all_file, candidate_file, expected_date,
                       benchmark_date, results):
    """Persist the freshness evidence the dashboard needs before showing a scan."""
    expected_text = str(expected_date)
    stock_dates = {
        row.get("symbol"): (
            None if row.get("candidate_status") == "ERROR"
            else row.get("analysis_date")
        )
        for row in results
    }
    stock_sources = {
        row.get("symbol"): (
            None if row.get("candidate_status") == "ERROR"
            else row.get("market_data_source")
        )
        for row in results
    }
    has_errors = any(row.get("candidate_status") == "ERROR" for row in results)
    insufficient_history = [
        row.get("symbol") for row in results
        if row.get("candidate_status") == "INSUFFICIENT_HISTORY"
    ]
    all_stock_dates_match = bool(stock_dates) and all(
        value == expected_text for value in stock_dates.values()
    )
    fresh = str(benchmark_date) == expected_text and all_stock_dates_match and not has_errors
    timestamp = all_file.stem.removeprefix("screening_results_")
    metadata_file = OUTPUT_DIR / f"scan_metadata_{timestamp}.json"
    metadata = {
        "schema_version": 1,
        "created_at": datetime.now().astimezone().isoformat(),
        "freshness_status": "FRESH" if fresh else "PARTIAL_OR_STALE",
        "expected_session": expected_text,
        "benchmark_date": str(benchmark_date),
        "stock_dates": stock_dates,
        "stock_data_sources": stock_sources,
        "insufficient_history_symbols": insufficient_history,
        "has_analysis_errors": has_errors,
        "results_file": all_file.name,
        "candidates_file": candidate_file.name,
    }
    temporary_file = metadata_file.with_suffix(".json.tmp")
    temporary_file.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    temporary_file.replace(metadata_file)
    return metadata_file


# ==========================================
# STOCK SCREENER
# ==========================================

def run_stock_screener(
    symbols=None,
    period=DEFAULT_PERIOD,
    limit=SCAN_LIMIT
):

    if symbols is None:
        symbols = load_universe()

    # Remove duplicates while preserving order.
    symbols = list(dict.fromkeys(
        symbol.strip().upper()
        for symbol in symbols
        if symbol and symbol.strip()
    ))

    if limit is not None:
        symbols = symbols[:limit]

    if not symbols:
        raise ValueError("No stocks available for screening")

    print("\n======================================")
    print("NSE FULL UNIVERSE TECHNICAL SCREENER")
    print("======================================")

    print(f"Stocks to scan: {len(symbols)}")
    print(f"Historical period: {period}")
    print(f"Universe file: {UNIVERSE_FILE}")

    # Fetch benchmark once.
    print("\nFetching Nifty 50 benchmark data...")

    benchmark_df = fetch_close_prices(INDEX_SYMBOL, period=period)

    if benchmark_df is None or benchmark_df.empty:
        raise ValueError(
            "Unable to fetch Nifty 50 benchmark data"
        )
    # ==========================================
    # MARKET DATA FRESHNESS GATE
    # ==========================================

    expected_date = get_latest_expected_nse_session()

    benchmark_date = get_latest_data_date(
        benchmark_df,
        "Nifty 50 benchmark"
    )

    print("\n========== DATA FRESHNESS CHECK ==========")

    print("Expected NSE session:", expected_date)
    print("Nifty latest candle:", benchmark_date)

    if benchmark_date != expected_date:
        raise RuntimeError(
            "STALE_DATA: Nifty 50 benchmark is outdated. "
            f"Expected={expected_date}, "
            f"Received={benchmark_date}. "
            "Screening stopped."
        )

    print("Benchmark freshness: PASSED")
    print(
        f"Nifty benchmark loaded: {len(benchmark_df)} candles"
    )

    results = []

    # Analyse each stock.
    for index, symbol in enumerate(symbols, start=1):

        print("\n--------------------------------------")
        print(f"[{index}/{len(symbols)}] Analysing {symbol}")
        print("--------------------------------------")

        try:

            technical_result = run_technical_analysis(
                symbol=symbol,
                period=period,
                benchmark_df=benchmark_df
            )

            row = extract_screening_row(
                technical_result
            )

            results.append(row)

            print(
                f"\n{symbol}: {row['candidate_status']}"
            )

            if row["rejection_reasons"]:
                print("Reasons:")

                for reason in row["rejection_reasons"].split(" | "):
                    print(f"  - {reason}")

        except Exception as error:

            print(
                f"ERROR analysing {symbol}: {error}"
            )

            results.append({
                "analysis_date": None,

                "symbol": symbol,
                "latest_price": None,
                "candidate_status": "ERROR",
                "trend_conditions_passed": None,
                "trend_template_pass": None,
                "relative_strength": None,
                "relative_strength_pass": None,
                "vcp_sequence_pass": None,
                "breakout_status": "ERROR",
                "breakout_confirmed": False,
                "rejection_reasons":
                    f"Analysis error: {error}",
                "error": str(error),
                "rank": "",
            })

    # Rank results.
    results = rank_results(results)

    # Save output files.
    all_file, candidate_file = save_results(results)
    metadata_file = save_scan_metadata(
        all_file, candidate_file, expected_date, benchmark_date, results
    )

    # Advance the local simulated trade book only on a fully fresh scan.
    if json.loads(metadata_file.read_text(encoding="utf-8")).get("freshness_status") == "FRESH":
        try:
            from forward_paper import process_fresh_scan
            paper_result = process_fresh_scan(all_file, expected_date, metadata_file)
            print("Forward paper book:", paper_result)
        except Exception as error:
            print("Forward paper book did not advance:", error)

    # Final summary.
    print("\n======================================")
    print("SCREENER SUMMARY")
    print("======================================")

    for row in results:

        print(
            f"{str(row['rank']):<5}"
            f"{row['symbol']:<15}"
            f"{str(row['candidate_status']):<22}"
            f"RS: {row['relative_strength']}"
        )

    qualified_count = sum(
        1 for row in results
        if row.get("candidate_status") == "BREAKOUT_CONFIRMED"
    )

    watch_count = sum(
        1 for row in results
        if row.get("candidate_status") == "SETUP_WATCH"
    )

    rejected_count = sum(
        1 for row in results
        if row.get("candidate_status") == "NOT_QUALIFIED"
    )

    error_count = sum(
        1 for row in results
        if row.get("candidate_status") == "ERROR"
    )

    print("\nTotal stocks scanned:", len(results))
    print("Confirmed breakouts:", qualified_count)
    print("Setup watch:", watch_count)
    print("Not qualified:", rejected_count)
    print("Analysis errors:", error_count)

    print("\nComplete results:", all_file)
    print("Breakout candidates:", candidate_file)
    print("Freshness metadata:", metadata_file)

    return results


# ==========================================
# MAIN
# ==========================================

if __name__ == "__main__":

    run_stock_screener()
