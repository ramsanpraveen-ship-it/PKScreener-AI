"""Fail-closed reader for completed screener outputs."""

import csv
import json
from pathlib import Path


def load_latest_scan(project_dir, expected_session):
    output_dir = Path(project_dir) / "data" / "screening_results"
    metadata_files = sorted(output_dir.glob("scan_metadata_*.json"))
    empty = {
        "status": "NO_VALIDATED_SCAN",
        "expected_session": str(expected_session),
        "latest_data_date": None,
        "message": "Run the screener after its freshness checks pass.",
        "candidates": [],
    }
    if not metadata_files:
        return empty

    # Never fall back to an older fresh scan if the latest scan is partial/stale.
    metadata_path = metadata_files[-1]
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {**empty, "status": "INVALID_SCAN_METADATA", "message": "Latest scan metadata cannot be read."}

    expected = str(expected_session)
    dates = metadata.get("stock_dates")
    latest_date = max((str(value) for value in (dates or {}).values()), default=None)
    if (metadata.get("schema_version") != 1
            or metadata.get("freshness_status") != "FRESH"
            or metadata.get("expected_session") != expected
            or metadata.get("benchmark_date") != expected
            or metadata.get("has_analysis_errors") is not False
            or not dates
            or any(str(value) != expected for value in dates.values())):
        return {
            **empty,
            "status": "STALE_OR_PARTIAL_DATA",
            "latest_data_date": latest_date,
            "message": "Latest scan did not prove matching fresh data for every stock and benchmark.",
        }

    results_name = metadata.get("results_file")
    if not isinstance(results_name, str) or Path(results_name).name != results_name:
        return {**empty, "status": "INVALID_SCAN_METADATA", "message": "Latest scan results path is invalid."}
    results_path = output_dir / results_name
    if not results_path.is_file():
        return {**empty, "status": "MISSING_SCAN_RESULTS", "message": "Latest validated scan result file is missing."}
    try:
        with results_path.open(newline="", encoding="utf-8") as source:
            rows = list(csv.DictReader(source))
    except (OSError, csv.Error):
        return {**empty, "status": "INVALID_SCAN_RESULTS", "message": "Latest scan result file cannot be read."}
    if not rows or any(row.get("analysis_date") != expected for row in rows):
        return {
            **empty,
            "status": "STALE_OR_PARTIAL_DATA",
            "latest_data_date": latest_date,
            "message": "The scan result rows do not all match the expected NSE session.",
        }
    return {
        "status": "FRESH",
        "expected_session": expected,
        "latest_data_date": latest_date,
        "message": "All recorded stock and benchmark dates match the expected NSE session.",
        "scan_created_at": metadata.get("created_at"),
        "candidates": rows,
    }
