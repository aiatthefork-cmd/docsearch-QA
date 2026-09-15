#!/usr/bin/env python3
"""Download annual reports from the SEC's EDGAR system into ./filings.

Filings are public domain. EDGAR asks that automated clients identify themselves
and stay under 10 requests a second; both are handled below.

    python fetch_filings.py --email you@example.com

The documents are saved exactly as filed. Run extract.py afterwards to turn them
into the text the search pipeline uses.
"""

import argparse
import json
import os
import sys
import time
import urllib.request

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
ARCHIVE_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{doc}"

DEFAULT_TICKERS = ["WERN", "HTLD"]
DEFAULT_YEARS = [2021, 2022, 2023]
RATE_LIMIT = 0.15


def get(url, email, as_json=False):
    req = urllib.request.Request(url, headers={
        "User-Agent": f"docsearch-prototype {email}",
        "Accept-Encoding": "gzip, deflate",
        "Host": url.split("/")[2],
    })
    time.sleep(RATE_LIMIT)
    with urllib.request.urlopen(req, timeout=90) as resp:
        raw = resp.read()
        if resp.headers.get("Content-Encoding") == "gzip":
            import gzip
            raw = gzip.decompress(raw)
    return json.loads(raw) if as_json else raw.decode("utf-8", "replace")


def resolve(tickers, email):
    data = get(TICKERS_URL, email, as_json=True)
    by_ticker = {v["ticker"].upper(): (v["cik_str"], v["title"]) for v in data.values()}
    out = {}
    for t in tickers:
        if t.upper() in by_ticker:
            out[t.upper()] = by_ticker[t.upper()]
        else:
            print(f"  ! {t}: not in EDGAR's ticker list", file=sys.stderr)
    return out


def annual_reports(cik, email, years):
    subs = get(SUBMISSIONS_URL.format(cik=cik), email, as_json=True)
    found = []
    for group in [subs["filings"]["recent"]]:
        for form, acc, doc, rpt in zip(group["form"], group["accessionNumber"],
                                       group["primaryDocument"], group["reportDate"]):
            if form == "10-K" and int(rpt[:4]) in years:
                found.append((int(rpt[:4]), acc.replace("-", ""), doc))
    for extra in subs["filings"].get("files", []):
        if len(found) >= len(years):
            break
        older = get(f"https://data.sec.gov/submissions/{extra['name']}", email, as_json=True)
        for form, acc, doc, rpt in zip(older["form"], older["accessionNumber"],
                                       older["primaryDocument"], older["reportDate"]):
            if form == "10-K" and int(rpt[:4]) in years:
                found.append((int(rpt[:4]), acc.replace("-", ""), doc))
    return sorted(set(found))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--email", required=True,
                    help="contact address for the EDGAR User-Agent header")
    ap.add_argument("--tickers", nargs="+", default=DEFAULT_TICKERS)
    ap.add_argument("--years", nargs="+", type=int, default=DEFAULT_YEARS)
    ap.add_argument("--out", default="filings")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    companies = resolve(args.tickers, args.email)
    index, total = [], 0

    for ticker, (cik, name) in companies.items():
        print(f"\n{ticker} - {name} (CIK {cik})")
        try:
            filings = annual_reports(cik, args.email, args.years)
        except Exception as exc:
            print(f"  ! could not list filings: {exc}")
            continue

        for year, acc, doc in filings:
            stem = f"{ticker.lower()}-10k-fy{year}"
            dest = os.path.join(args.out, stem + ".htm")
            url = ARCHIVE_URL.format(cik=cik, acc=acc, doc=doc)
            if not os.path.exists(dest):
                try:
                    raw = get(url, args.email)
                except Exception as exc:
                    print(f"  ! FY{year}: {exc}")
                    continue
                with open(dest, "w", encoding="utf-8", newline="\n") as fh:
                    fh.write(raw)
            size = os.path.getsize(dest)
            total += size
            index.append({"doc_id": stem, "ticker": ticker, "company": name,
                          "fiscal_year": year, "form": "10-K",
                          "source_url": url, "file": os.path.basename(dest),
                          "bytes": size})
            print(f"  + FY{year}  {size:>11,} bytes  {dest}")

    with open(os.path.join(args.out, "index.json"), "w", encoding="utf-8") as fh:
        json.dump({"filings": index}, fh, indent=1)

    print(f"\n{len(index)} filings, {total:,} bytes ({total/1e6:.1f} MB) in {args.out}/")
    print("next: python extract.py")


if __name__ == "__main__":
    main()
