# Kaggle Nifty 500 Dataset Assessment

**Dataset:** [shreyashautomation/nifty500-companies-5-years-stock-market-data](https://www.kaggle.com/datasets/shreyashautomation/nifty500-companies-5-years-stock-market-data)
**Downloaded version:** 2
**Assessment date:** 27 November 2026
**Decision:** useful candidate for exploratory cross-checking; **not accepted as five-year walk-forward evidence**.

## Local files and observed structure

The archive is held only in the ignored local cache under `data/kagglehub-cache/` and is not committed:

| File | Rows | Tickers | Dates | Main issues |
| --- | ---: | ---: | --- | --- |
| `nifty500_5yr_data.csv` | 551,643 | 500 | 2021-06-09 to 2026-06-09 (1,235 dates) | Ticker coverage varies from 113 to 1,235 rows; one close exceeds the recorded high at raw precision by less than 1e-6 (the inventory tolerance check reports 0 invalids); ends about 5 months before assessment date. |
| `nifty500_complete_daily_data.csv` | 619,236 | 501 | 2021-06-24 to 2026-06-22 (1,236 dates) | 65,279 rows have all five OHLCV fields null; 2,131 rows have zero volume with prices present; rectangular ticker/date grid does not establish that carried/empty rows are valid exchange observations. |

Both files have `Date` and `Ticker` keys with no duplicate key pairs in this scan. The second file contains one ticker (`VOGL`) not present in the first. The first file's `Notes` column records the 1 February 2026 special session for 465 rows.

SHA-256 checksums from the downloaded version:

- `nifty500_5yr_data.csv`: `74ad16d3135685880ccde748bffe58da0d13b255f190443a9f7a3b0200b648eb`
- `nifty500_complete_daily_data.csv`: `05791b2055569ff0d005b6a8093f816d8b71f29c376bd97be185ea23a31c6680`

## Why it cannot support the required validation yet

- The files stop in June 2026 and do not cover the recent five months needed for a rolling five-year window ending in November 2026.
- The archive does not provide point-in-time Nifty 500 membership intervals. Its ticker panel cannot establish historical inclusion/exclusion dates or correct survivorship treatment.
- No Nifty 50 TRI or Nifty 500 TRI benchmark series was included in either CSV.
- Downloaded files alone do not provide verified source lineage, corporate-action event records, dividend cash flows, delisted/merged coverage, or proof whether OHLC values are raw, split-adjusted, or dividend-adjusted.
- Missing OHLCV and zero-volume rows require explicit exchange-session interpretation; they must not be forward-filled or treated as real fills without corroboration.
- The observed OHLC range discrepancy must be investigated and documented. Do not silently repair data.

## Reproduction

The retrieval/inventory helper is `tools/download_kaggle_nifty500.py`. It downloads through KaggleHub and prints file size, SHA-256, schema, date range, symbols, nulls, duplicate rows, zero volumes, and OHLC-range checks. Exact local archive path:

```text
data/kagglehub-cache/datasets/shreyashautomation/nifty500-companies-5-years-stock-market-data/versions/2
```

The two data files are ignored by Git and remain local. Do not use this assessment as a source certification. Before any replay, cross-check stock sessions and adjustment factors against primary/official sources, obtain point-in-time constituents including delisted and merged companies, acquire reliable total-return benchmarks, and extend to the required window.
