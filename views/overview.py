"""Overview: plain-language guide to each dataset, what it shows and why it is used.

Every number and every 'Meaning' sentence is computed from the current data, so the
page stays correct when new filings arrive.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from ai_capital_cycle.capital import latest_complete
from ai_capital_cycle.network import filter_deals, find_loops, load_deals, node_table
from ai_capital_cycle.universe import BY_TICKER
from views import capital_cycle, demand_view, network_view

B = 1e9
BIG_THREE = ("AMZN", "GOOGL", "MSFT")


def _bn(x) -> str:
    if pd.isna(x):
        return "n/a"
    return f"${x / 1e12:,.2f} trillion" if abs(x) >= 1e12 else f"${x / B:,.0f}B"


def _pct(x, signed=False) -> str:
    return "n/a" if pd.isna(x) else (f"{x:+.0%}" if signed else f"{x:.0%}")


def _money(x) -> str:
    return "n/a" if pd.isna(x) else f"${x:.2f}"


def _year_ago(frame: pd.DataFrame, quarter) -> pd.Series | None:
    prior = frame[frame["calendar_quarter"] == quarter - 4]
    return None if prior.empty else prior.iloc[0]


def _get(row, key):
    return float("nan") if row is None else row[key]


def _table(rows: list[tuple[str, str, str]] | list[tuple[str, str, str, str]], columns: list[str]) -> None:
    st.dataframe(pd.DataFrame(rows, columns=columns), hide_index=True, width="stretch")


def _capital_section() -> None:
    st.markdown("### 1. Company cash-flow data")
    st.caption("Used in the **Capital cycle** tab")
    st.markdown(
        "**What it is:** the official numbers from each company's quarterly and annual reports (10-Q and 10-K) "
        "filed with the SEC: how much they spend on data centres and equipment (CapEx), how much cash their "
        "business brings in, revenue, depreciation, borrowing, buybacks and dividends. Companies: Microsoft, "
        "Amazon, Alphabet, Meta, Oracle and CoreWeave (the spenders), plus Nvidia (the supplier).\n\n"
        "**How it's collected:** downloaded automatically from SEC every Monday. Each number keeps a link to the "
        "exact filing it came from.\n\n"
        "**Why it's used:** it answers *how much is being spent, and can the companies afford it?* These are "
        "audited, legally filed numbers, the most reliable there are.")

    tickers = tuple(sorted(capital_cycle.SPENDERS))
    _, _, ttm, agg, _ = capital_cycle._compute(capital_cycle.FACTS_PATH.stat().st_mtime, None, tickers)
    row = latest_complete(agg)
    if row is None:
        st.info("Not enough data yet.")
        return
    prior = _year_ago(agg, row["calendar_quarter"])

    # Compare this year's growth with the oldest growth rate available in the past year
    # (a year ago where it exists; CoreWeave's short history can make that missing).
    earlier, months = float("nan"), 0
    for back in (4, 3, 2):
        past = agg[agg["calendar_quarter"] == row["calendar_quarter"] - back]
        if not past.empty and pd.notna(past.iloc[0]["capex_yoy"]):
            earlier, months = past.iloc[0]["capex_yoy"], back * 3
            break
    if pd.isna(row["capex_yoy"]):
        spend_meaning = "Growth not yet measurable"
    elif row["capex_yoy"] < 0:
        spend_meaning = "Spending is falling"
    elif pd.isna(earlier):
        spend_meaning = "Spending is growing; not enough history to tell if it is speeding up"
    elif row["capex_yoy"] > earlier:
        spend_meaning = f"Growth is speeding up ({_pct(earlier, True)} {months} months ago)"
    else:
        spend_meaning = f"Still growing, but more slowly ({_pct(earlier, True)} {months} months ago)"

    rr = row["reinvestment_rate"]
    rr_meaning = ("They spend more than their businesses bring in" if rr > 1 else
                  "Most of the cash their businesses earn now goes into building" if rr > 0.6 else
                  "Spending is well covered by the cash coming in")

    prior_fcf = _get(prior, "free_cash_flow")
    fcf_meaning = ("Not enough history to compare" if pd.isna(prior_fcf) else
                   "Shrinking as spending grows" if row["free_cash_flow"] < prior_fcf else
                   "Growing despite higher spending")

    debt = row["debt_funding_share"]
    debt_meaning = ("Borrowing is funding a growing share of the build-out"
                    if pd.notna(debt) and debt > _get(prior, "debt_funding_share") and debt > 0.15 else
                    "Borrowing covers part of the build-out" if pd.notna(debt) and debt > 0.15 else
                    "Little of the build-out is funded by new borrowing")

    q = str(row["calendar_quarter"])
    rows = [
        ("Spending (CapEx)", f"{_bn(row['capex'])}, {_pct(row['capex_yoy'], True)} in a year", spend_meaning),
        ("Spending ÷ cash coming in", _pct(rr), rr_meaning),
        ("Cash left after spending", _bn(row["free_cash_flow"]), fcf_meaning),
        ("Paid for with new borrowing", _pct(debt), debt_meaning),
    ]
    latest = ttm[(ttm["calendar_quarter"] == row["calendar_quarter"]) & ttm["ticker"].isin(tickers)]
    stretched = latest[latest["reinvestment_rate"] > 1].sort_values("reinvestment_rate", ascending=False)
    if not stretched.empty:
        parts = [f"{BY_TICKER[t].name} {r:.1f}×" for t, r in zip(stretched["ticker"], stretched["reinvestment_rate"])]
        listed = parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]
        rows.append(("Spending more than they earn", listed,
                     "These companies spend more than the cash their business brings in, "
                     "so they rely on borrowing or savings"))
    st.markdown(f"**What it shows** (last 12 months, to {q}):")
    _table(rows, ["", "Finding", "Meaning"])


def _demand_section() -> None:
    st.markdown("### 2. Cloud sales and signed contracts")
    st.caption("Used in the **Demand** tab charts")
    st.markdown(
        "**What it is:** the breakdown inside the same filings: AWS sales, Google Cloud sales, Microsoft's cloud "
        "division, Oracle's cloud infrastructure, CoreWeave's sales, Nvidia's data-centre chip sales, and signed "
        "future contracts. SEC's simple download leaves these out, so the app reads each filing's full data file.\n\n"
        "**How it's collected:** also automatic and weekly, with a filing link for every number. The app checks "
        "that the quarters add up to the audited yearly totals.\n\n"
        "**Why it's used:** dataset 1 shows the *spending*; this one shows whether *customers are paying* for "
        "what's being built.")

    if not demand_view.SEGMENTS_PATH.exists():
        st.info("Segment data has not been downloaded yet.")
        return
    *_, agg = demand_view._compute(demand_view.SEGMENTS_PATH.stat().st_mtime,
                                   demand_view.FACTS_PATH.stat().st_mtime, None, BIG_THREE, 4)
    if agg.empty:
        st.info("Not enough data yet.")
        return
    row = agg.iloc[-1]
    prior = _year_ago(agg, row["calendar_quarter"])

    def compare(now, before, up: str, down: str) -> str:
        if pd.isna(now) or pd.isna(before):
            return "Not enough history to compare"
        return up if now > before else down

    rows = [
        ("Cloud sales growth", _pct(row["cloud_revenue_growth"], True), _pct(_get(prior, "cloud_revenue_growth"), True),
         compare(row["cloud_revenue_growth"], _get(prior, "cloud_revenue_growth"),
                 "Customer demand is growing faster", "Customer demand is growing more slowly")),
        ("Cloud sales per $1 spent", _money(row["revenue_per_capex"]), _money(_get(prior, "revenue_per_capex")),
         compare(row["revenue_per_capex"], _get(prior, "revenue_per_capex"),
                 "Sales are keeping up with spending", "Spending is growing faster than sales")),
        ("New profit per $1 spent the year before", _pct(row["incremental_income_per_capex"]),
         _pct(_get(prior, "incremental_income_per_capex")),
         compare(row["incremental_income_per_capex"], _get(prior, "incremental_income_per_capex"),
                 "New investment is earning more than before", "New investment is earning less than before")),
        ("Signed future contracts", _bn(row["backlog"]), _bn(_get(prior, "backlog")),
         compare(row["backlog"], _get(prior, "backlog"),
                 "Customers have committed to more future business", "Committed future business has shrunk")),
    ]
    st.markdown(f"**What it shows** (AWS, Google Cloud and Microsoft, last 12 months to {row['calendar_quarter']}):")
    _table(rows, ["", "Now", "A year ago", "Meaning"])
    st.markdown("The key question: when spending runs ahead of today's sales, the bet is that signed contracts "
                "turn into real payments.")


def _network_section() -> None:
    st.markdown("### 3. Deals between companies")
    st.caption("Used in the 3D **Who pays whom** map on the Demand tab")
    deals = load_deals(network_view.DEALS_PATH)
    st.markdown(
        f"**What it is:** {len(deals)} deals between AI companies: investments, cloud contracts, chip purchases and "
        "chip manufacturing, each with an amount (where known), a date, a status and a source link.\n\n"
        "**How it's collected:** by hand, from company announcements, SEC filings (including Anthropic's IPO "
        "filing) and news reports. Unlike datasets 1 and 2, it is not updated automatically.\n\n"
        "**Why it's used:** filings show each company on its own. This shows how they are tied together, which "
        "matters because money can go in a circle.")
    shown = filter_deals(deals)
    nodes = node_table(shown)
    loops = find_loops(shown, max_length=3)
    top = nodes.head(3)
    hubs = ", then ".join(f"{r.company} ({r.connections})" for r in top.itertuples())
    rows = [
        ("Most connected", hubs, "The companies the whole web of deals runs through"),
        ("Money loops", f"{len(loops)} loops of 2–3 companies",
         "Money paid out comes back: e.g. Nvidia invests in OpenAI, and OpenAI buys Nvidia chips"),
    ]
    _table(rows, ["", "Finding", "Meaning"])
    st.markdown("Why loops matter: when a supplier funds its own customers, part of its sales is paid for with its "
                "own money. Some demand then depends on the investment cycle continuing, not only on end customers.\n\n"
                "**Limits:** amounts are what was announced, often 'up to' or spread over many years, not money "
                "already paid. Deals marked 'press reports only' are not confirmed by the companies. Latest deal: "
                f"{deals['announced'].max():%d %b %Y}.")


def _sample_section() -> None:
    st.markdown("### 4. Sample industry file")
    st.caption("Only in the **Project model** tab")
    st.markdown("A small made-up example file, labelled HYPOTHETICAL, that demonstrates the upload tool. It contains "
                "no real findings, and the Capital cycle and Demand tabs don't use it.")


def render() -> None:
    st.markdown("The app uses three real datasets. Each answers one question:\n\n"
                "1. **How much is being spent?** (company cash-flow data)\n"
                "2. **Are customers paying for it?** (cloud sales and signed contracts)\n"
                "3. **How much of the demand is the industry funding itself?** (deals between companies)")
    _capital_section()
    st.divider()
    _demand_section()
    st.divider()
    _network_section()
    st.divider()
    _sample_section()
    st.divider()
    st.caption("One limit applies to all of them: no company reports AI spending separately, so these are "
               "whole-company figures (Amazon's include warehouses, for example). The direction over time is the "
               "most meaningful signal. Figures update automatically as new filings arrive. Not investment advice.")
