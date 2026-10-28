"""One-off survey: which dimensional revenue / income / backlog facts each company files.

Writes data/_survey/segment_survey.json. Temporary; used to design Module B.
"""
from __future__ import annotations

import json
import sys
import traceback
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ai_capital_cycle.sec import user_agent  # noqa: E402
from ai_capital_cycle.universe import UNIVERSE  # noqa: E402
from ai_capital_cycle.xbrl_instance import (SUBMISSIONS, instance_url, parse_instance,  # noqa: E402
                                            recent_periodic_filings)

PATTERN = r"Revenue|OperatingIncomeLoss|RemainingPerformanceObligation|Backlog|ConcentrationRisk|CostOfRevenue|Depreciation|PaymentsToAcquire"


def main() -> None:
    session = requests.Session()
    session.headers.update({"User-Agent": user_agent(), "Accept-Encoding": "gzip, deflate"})
    out = {}
    for company in UNIVERSE:
        try:
            out[company.ticker] = survey_company(session, company)
        except Exception:  # record and continue: this is a diagnostic script
            out[company.ticker] = {"error": traceback.format_exc()[-3000:]}
        print(company.ticker, "done", flush=True)
        path = ROOT / "data" / "_survey" / "segment_survey.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(out, indent=1, default=str))


def survey_company(session, company) -> dict:
    if True:
        r0 = session.get(SUBMISSIONS.format(cik10=company.cik10), timeout=30)
        if not r0.ok:
            return {"error": f"submissions HTTP {r0.status_code}"}
        subs = r0.json()
        filings = recent_periodic_filings(subs)
        result = {"filings_listed": len(filings), "samples": []}
        picks = [filings[filings.form == "10-Q"].head(1), filings[filings.form == "10-K"].head(1),
                 filings[filings.form == "10-K"].iloc[2:3]]
        for pick in picks:
            if pick.empty:
                continue
            f = pick.iloc[0]
            url = instance_url(company.cik, f.accessionNumber, f.primaryDocument)
            time.sleep(0.3)
            r = session.get(url, timeout=60)
            sample = {"form": f.form, "filed": f.filingDate, "report": f.reportDate, "url": url, "status": r.status_code}
            if r.ok:
              try:
                df = parse_instance(r.content)
                sample["facts"] = int(len(df))
                df = df[df.concept.str.contains(PATTERN) & (df.unit.str.lower().str.contains("usd") | df.unit.str.lower().str.contains("pure"))]
                end = df.end.max()
                cur = df[df.end == end].copy()
                cur["days"] = (cur.end - cur.start).dt.days + 1
                cur["axes"] = cur.dims.str.replace(r"=[^;]*", "", regex=True)
                sample["axes_by_concept"] = (cur.groupby("concept")["axes"].apply(lambda s: sorted(set(s))).to_dict())
                keep = cur[cur.concept.str.contains("Revenue|OperatingIncomeLoss|RemainingPerformanceObligation|Backlog")
                           & ((cur.days.isna()) | (cur.days < 100) | (cur.days > 350))]
                sample["facts_at_period_end"] = [
                    {"c": row.concept, "v": row.value, "d": None if row.days != row.days else int(row.days),
                     "dims": row.dims} for row in keep.itertuples()][:400]
              except Exception:
                sample["error"] = traceback.format_exc()[-3000:]
                sample["head"] = r.content[:300].decode("utf-8", "replace")
            result["samples"].append(sample)
        return result


if __name__ == "__main__":
    main()
