"""Download SEC XBRL facts for the company universe into data/sec_facts.csv.

Usage:  SEC_USER_AGENT="Your Name you@example.com" python scripts/refresh_sec_data.py
Run weekly by .github/workflows/refresh-sec-data.yml.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ai_capital_cycle.sec import download_universe  # noqa: E402
from ai_capital_cycle.universe import UNIVERSE  # noqa: E402


def main() -> None:
    facts = download_universe(progress=lambda c: print(f"Fetching {c.ticker} ({c.name})", flush=True))
    facts = facts.sort_values(["ticker", "tag", "end", "start", "filed", "accession"]).reset_index(drop=True)
    data_dir = ROOT / "data"
    data_dir.mkdir(exist_ok=True)
    facts.to_csv(data_dir / "sec_facts.csv", index=False)
    meta = {
        "source": "SEC EDGAR XBRL companyfacts API (data.sec.gov)",
        "retrieved_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "latest_filing_date": str(facts["filed"].max()),
        "rows": int(len(facts)),
        "companies": {c.ticker: int((facts.ticker == c.ticker).sum()) for c in UNIVERSE},
    }
    (data_dir / "sec_facts_meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    print(json.dumps(meta, indent=2))


if __name__ == "__main__":
    main()
