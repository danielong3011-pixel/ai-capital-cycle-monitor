"""Methodology, definitions and limitations."""
import json
from pathlib import Path

import streamlit as st

from ai_capital_cycle.universe import UNIVERSE

ROOT = Path(__file__).resolve().parents[1]

METHOD = """
#### Research question
Is the AI industry generating enough economic value to justify the capital being invested, and what
financial conditions could make the current investment cycle unsustainable? This tool measures
conditions; it does not predict when, or whether, a downturn happens. High CapEx, fast growth or high
valuations are not by themselves evidence of a bubble.

#### Data
SEC EDGAR XBRL *company facts* from 10-K and 10-Q filings, refreshed weekly by a GitHub Action.
Every quarterly figure keeps the accession number of the filing it came from (see *Data provenance*
on the Capital cycle tab).

#### From filings to calendar quarters
1. **Tag selection.** Companies use different XBRL tags for the same line (Amazon and Nvidia report
   CapEx as `PaymentsToAcquireProductiveAssets`, others as `PaymentsToAcquirePropertyPlantAndEquipment`).
   Each line item has an ordered tag list, with per-company overrides where needed.
2. **Restatements.** For each period the most recently filed value is used. The point-in-time setting
   restricts to filings available on a chosen date, so past readings can be reproduced without
   look-ahead bias.
3. **Discrete quarters.** 10-Q cash-flow statements are year-to-date, so quarters are derived by
   differencing cumulative values; if a year has an annual figure and three quarters, the fourth is the
   annual figure less the other three. Directly reported quarters take precedence.
4. **Calendar alignment.** Fiscal quarters map to the calendar quarter containing their midpoint
   (Microsoft's fiscal year ends in June, Oracle's in May, Nvidia's in late January).
5. **TTM.** Four consecutive calendar quarters; a gap gives no value rather than a partial sum.
6. **Coverage.** The aggregate only reports quarters in which every selected company has filed, so a
   late filer cannot look like a fall in spending.

#### Definitions (all TTM)
| Measure | Definition |
|---|---|
| CapEx | Cash purchases of property and equipment |
| Free cash flow | Operating cash flow − CapEx |
| Reinvestment rate | CapEx ÷ operating cash flow |
| Capital intensity | CapEx ÷ revenue |
| CapEx ÷ depreciation | Matched sample of companies reporting quarterly D&A |
| Funding gap | CapEx + buybacks + dividends − operating cash flow |
| Net debt issuance | Debt issued − debt repaid + net short-term borrowing |
| Debt-funded share | Net debt issuance ÷ CapEx |
| Concentration (HHI) | Sum of squared CapEx shares |

Ratios for the aggregate are computed from summed flows, so larger spenders carry more weight.

#### Avoiding double counting
The same dollar appears at several points along the chain: an Nvidia GPU sale is Nvidia's revenue and
a hyperscaler's CapEx. Companies are assigned a role (*spender* or *supplier*) and aggregates sum
within a role only. Supplier revenue is shown as a ratio to spender CapEx, never added to it.

#### Demand (Module B)
Segment revenue, segment operating income and backlog are not in SEC's company-facts service, so they are
read from each filing's full XBRL document, matched by concept and segment or product label
(`src/ai_capital_cycle/segments.py`), and put through the same quarter, calendar and restatement logic.
Segment recasts (such as Microsoft's in 2024) are handled by using the latest filed figure for each period.

| Measure | Definition (TTM) |
|---|---|
| Cloud revenue | AWS, Google Cloud, Microsoft Intelligent Cloud, Oracle Cloud Infrastructure, CoreWeave (selectable) |
| Revenue per $ of CapEx | Cloud revenue ÷ the same companies' total CapEx |
| New revenue per $ of CapEx | (Cloud revenue − cloud revenue a year earlier) ÷ CapEx over the twelve months ending *lag* quarters earlier |
| New profit per $ of CapEx | Same, with segment operating income: a rough pre-tax incremental return |
| Signed future contracts | Money customers have agreed to pay but haven't been charged yet (accounting term: backlog, or remaining performance obligations) |
| Future contracts per $ of CapEx | Signed future contracts ÷ TTM CapEx |

**Layers of the value chain.** (1) Suppliers: Nvidia's Data Center revenue is the clouds' CapEx.
(2) Compute providers: part of cloud revenue is AI labs' spending. (3) AI model and application
companies: their revenue is spending by final customers. The only audited view of layer 3 in the
filings is Microsoft's disclosure of OpenAI's revenue. Layers are shown side by side and never added up.
Meta, which sells no cloud services, is shown separately: its AI investment pays off through advertising.

**Caveats.** Microsoft's Intelligent Cloud segment includes server software as well as Azure. Signed future contracts are
company-wide for Amazon, Alphabet (before 2026), Microsoft (commercial) and Oracle. Because CapEx is
whole-company, the ratios understate returns on cloud investment alone; their direction over time is the
signal.

#### Known limitations
- **Total, not AI-only.** Reported CapEx covers all of a company's investment (Amazon's includes
  retail logistics). No AI share is assumed.
- **Finance leases.** Data-centre capacity acquired under finance leases (large at Microsoft) is not in
  cash CapEx. Lease principal repayments appear in financing.
- **Off-balance-sheet structures**, such as joint-venture data centres, are not captured.
- **Coverage.** Private labs and non-US companies (e.g. TSMC, which files 20-F) are not included yet.
- **Imputed zeros.** Optional financing lines (debt issued, buybacks, dividends…) are treated as zero in
  a quarter where the company filed a cash-flow statement but did not report the line.
- **Nominal USD**, no inflation adjustment.

Not investment advice.
"""


def render() -> None:
    st.markdown(METHOD)
    st.markdown("#### Company universe")
    st.dataframe([{"Ticker": c.ticker, "Company": c.name, "Role": c.role.replace("_", " "), "CIK": c.cik,
                   "Note": c.note} for c in UNIVERSE], hide_index=True, width="stretch")
    meta_path = ROOT / "data" / "sec_facts_meta.json"
    if meta_path.exists():
        meta = json.loads(meta_path.read_text())
        st.caption(f"Snapshot retrieved {meta['retrieved_utc']} · {meta['rows']:,} facts · "
                   f"latest filing {meta['latest_filing_date']}.")
