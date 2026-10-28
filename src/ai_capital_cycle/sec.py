"""Download and flatten SEC EDGAR XBRL "company facts".

Source: https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json
SEC asks automated clients to identify themselves in the User-Agent header and
to stay under 10 requests per second. Set the SEC_USER_AGENT environment variable
(e.g. "Your Name your@email.com") to identify yourself; a project default is used
otherwise.

The output is a long table with one row per reported fact and full provenance
(accession number, form, filing date), so any figure in the app can be traced to
the filing it came from.
"""
from __future__ import annotations

import os
import time
from collections.abc import Iterable

import pandas as pd

from .universe import UNIVERSE, Company, all_tags

COMPANYFACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik10}.json"
DEFAULT_USER_AGENT = "ai-capital-cycle-monitor github.com/danielong3011-pixel/ai-capital-cycle-monitor"
ACCEPTED_FORMS = frozenset({"10-K", "10-K/A", "10-Q", "10-Q/A", "10-KT", "10-KT/A"})
FACT_COLUMNS = ["ticker", "cik", "tag", "start", "end", "value_usd", "accession", "form",
                "fiscal_year", "fiscal_period", "filed"]
EARLIEST_PERIOD_END = "2016-01-01"


def user_agent() -> str:
    return os.environ.get("SEC_USER_AGENT", "").strip() or DEFAULT_USER_AGENT


def fetch_companyfacts(company: Company, session=None, timeout: float = 30.0) -> dict:
    """Return the raw companyfacts JSON for one company."""
    import requests

    http = session or requests
    response = http.get(COMPANYFACTS_URL.format(cik10=company.cik10),
                        headers={"User-Agent": user_agent(), "Accept-Encoding": "gzip, deflate"},
                        timeout=timeout)
    response.raise_for_status()
    return response.json()


def flatten_companyfacts(payload: dict, company: Company, tags: Iterable[str] | None = None,
                         earliest_end: str = EARLIEST_PERIOD_END) -> pd.DataFrame:
    """Flatten the USD facts for the requested us-gaap tags into FACT_COLUMNS rows.

    Only 10-K/10-Q family forms are kept (8-K press-release facts are unaudited
    and duplicate the periodic reports). Instant (balance-sheet) facts are dropped
    because every concept used here is a flow over a period.
    """
    wanted = set(tags) if tags is not None else all_tags()
    gaap = payload.get("facts", {}).get("us-gaap", {})
    rows = []
    for tag in sorted(wanted & gaap.keys()):
        for fact in gaap[tag].get("units", {}).get("USD", []):
            if fact.get("form") not in ACCEPTED_FORMS or "start" not in fact:
                continue
            if fact["end"] < earliest_end:
                continue
            rows.append((company.ticker, company.cik, tag, fact["start"], fact["end"], float(fact["val"]),
                         fact.get("accn"), fact.get("form"), fact.get("fy"), fact.get("fp"), fact.get("filed")))
    frame = pd.DataFrame(rows, columns=FACT_COLUMNS)
    return frame.drop_duplicates().reset_index(drop=True)


def download_universe(companies: Iterable[Company] = UNIVERSE, pause: float = 0.2,
                      progress=None) -> pd.DataFrame:
    """Download and flatten facts for every company. Pauses between requests."""
    import requests

    frames = []
    with requests.Session() as session:
        for i, company in enumerate(companies):
            if i:
                time.sleep(pause)
            if progress:
                progress(company)
            frames.append(flatten_companyfacts(fetch_companyfacts(company, session), company))
    return pd.concat(frames, ignore_index=True)


def load_facts(path) -> pd.DataFrame:
    """Read a facts snapshot written by scripts/refresh_sec_data.py."""
    frame = pd.read_csv(path, dtype={"ticker": str, "tag": str, "accession": str, "form": str,
                                     "fiscal_period": str})
    missing = set(FACT_COLUMNS) - set(frame.columns)
    if missing:
        raise ValueError(f"Facts file is missing columns: {', '.join(sorted(missing))}")
    return frame[FACT_COLUMNS]
