"""Download segment/product/backlog series from each 10-K and 10-Q XBRL instance.

Incremental: filings already listed in data/sec_segment_filings.csv are skipped,
so weekly runs only fetch new filings. Writes data/sec_segments.csv.

Usage:  SEC_USER_AGENT="Your Name you@example.com" python scripts/refresh_segment_data.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ai_capital_cycle.sec import user_agent  # noqa: E402
from ai_capital_cycle.segments import SEGMENT_COLUMNS, SERIES, extract_from_filing  # noqa: E402
from ai_capital_cycle.universe import BY_TICKER  # noqa: E402
from ai_capital_cycle.xbrl_instance import SUBMISSIONS, instance_url, recent_periodic_filings  # noqa: E402

DATA = ROOT / "data"
SEGMENTS = DATA / "sec_segments.csv"
FILINGS = DATA / "sec_segment_filings.csv"
SINCE = "2019-06-01"   # inline XBRL became mandatory for large filers from mid-2019


def main() -> None:
    session = requests.Session()
    session.headers.update({"User-Agent": user_agent(), "Accept-Encoding": "gzip, deflate"})
    done = pd.read_csv(FILINGS, dtype=str) if FILINGS.exists() else pd.DataFrame(
        columns=["ticker", "accession", "form", "filed", "status", "rows"])
    facts = pd.read_csv(SEGMENTS, dtype=str, keep_default_na=False) if SEGMENTS.exists() else pd.DataFrame(
        columns=SEGMENT_COLUMNS)
    new_facts, new_log = [], []
    for ticker in sorted({s.ticker for s in SERIES}):
        company = BY_TICKER[ticker]
        subs = session.get(SUBMISSIONS.format(cik10=company.cik10), timeout=30)
        subs.raise_for_status()
        filings = recent_periodic_filings(subs.json(), since=SINCE)
        todo = filings[~filings["accessionNumber"].isin(done.loc[done.status == "ok", "accession"])]
        print(f"{ticker}: {len(filings)} filings, {len(todo)} to fetch", flush=True)
        for f in todo.itertuples():
            time.sleep(0.15)
            url = instance_url(company.cik, f.accessionNumber, f.primaryDocument)
            try:
                r = session.get(url, timeout=90)
                if not r.ok:
                    new_log.append((ticker, f.accessionNumber, f.form, f.filingDate, f"HTTP {r.status_code}", 0))
                    continue
                rows = extract_from_filing(r.content, ticker, f.accessionNumber, f.form, f.filingDate)
                new_facts.append(rows)
                new_log.append((ticker, f.accessionNumber, f.form, f.filingDate, "ok", len(rows)))
            except Exception as error:  # keep going; the log records the failure for the next run
                new_log.append((ticker, f.accessionNumber, f.form, f.filingDate, f"error: {error}"[:200], 0))
    log = pd.DataFrame(new_log, columns=["ticker", "accession", "form", "filed", "status", "rows"])
    done = pd.concat([done[~done.accession.isin(log.accession)], log], ignore_index=True)
    if new_facts:
        add = pd.concat(new_facts, ignore_index=True)
        for col in ("start", "end"):
            add[col] = pd.to_datetime(add[col]).dt.strftime("%Y-%m-%d").fillna("")
        facts = pd.concat([facts, add.astype(str)], ignore_index=True)
    facts = facts.drop_duplicates().sort_values(["ticker", "series", "end", "start", "filed", "accession"])
    DATA.mkdir(exist_ok=True)
    facts.to_csv(SEGMENTS, index=False)
    done.sort_values(["ticker", "filed", "accession"]).to_csv(FILINGS, index=False)
    print(log.groupby(["ticker", "status"]).size().to_string())
    print(f"{len(facts)} segment facts in total")


if __name__ == "__main__":
    main()
