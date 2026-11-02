# Data

Nothing in this directory except this file, `download_sec.py` and
`manifest.json` is committed.

## Source

Public XBRL company facts from SEC EDGAR, through the JSON APIs at
`data.sec.gov`:

| What | URL pattern | Used for |
|---|---|---|
| frames | `api/xbrl/frames/us-gaap/Assets/USD/CY2012Q4I.json` and `CY2023Q4I.json` | universe selection |
| company facts | `api/xbrl/companyfacts/CIK##########.json` | every line item of every company |
| submissions | `submissions/CIK##########.json` and its continuation files | form types, amended filings, 8-K items |

The data are "as filed" by the registrants. The SEC says it cannot guarantee
their accuracy and that they are not a substitute for the filings. The same
holds for everything derived from them here.

## Access policy

The script sends the user agent `Julia Kowalczuk j.kowalczuk326@gmail.com`
(set `EGR_USER_AGENT` to use your own name and address, which the SEC asks
for) and waits at least 0.15 seconds between requests, well under the SEC's
stated maximum of 10 requests per second. It retries on connection errors and
on HTTP 429 and 503 with an increasing wait.

## Pinning

Every downloaded file is written under `data/raw/` and recorded in
`data/manifest.json` with its URL, retrieval date (UTC) and SHA-256. The
manifest is committed. A later download that gets a different file (the SEC
updates these records as filings arrive) is recorded with the new checksum
and date; `python data/download_sec.py --check` compares the files on disk
with the manifest and lists the differences, and `--strict` makes a
difference an error. The results in this repository were produced from the
files whose checksums are in the committed manifest.

## Layout

```
data/
  manifest.json                 committed
  raw/
    frames/                     two frames responses
    companyfacts/CIK##########.json
    submissions/CIK##########.json, CIK##########-submissions-001.json ...
  processed/                    written by `egr prepare`, not committed
```

## Running

```
python data/download_sec.py            # universe, then company facts and submissions
python data/download_sec.py --quick    # the 24-company quick universe
python data/download_sec.py --check    # compare files on disk with the manifest
```

Set `EGR_DATA_DIR` to keep the raw files outside the repository.
