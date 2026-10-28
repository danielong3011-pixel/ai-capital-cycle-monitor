"""Module B: is AI infrastructure spending backed by customer demand?"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from ai_capital_cycle.capital import company_ttm
from ai_capital_cycle.demand import (BACKLOG, CLOUD_REVENUE, DEFAULT_PROVIDERS, aggregate_providers,
                                     backlog_points, flow_quarters, provider_table, ttm, wide)
from ai_capital_cycle.periods import build_panel
from ai_capital_cycle.sec import load_facts
from ai_capital_cycle.segments import SERIES, SERIES_BY_NAME, load_segments
from views.capital_cycle import (COLOR, PALETTE, PLOT_CONFIG, B, _filing_url, _fmt_bn, _fmt_pct, _layout, _q)

ROOT = Path(__file__).resolve().parents[1]
SEGMENTS_PATH = ROOT / "data" / "sec_segments.csv"
FACTS_PATH = ROOT / "data" / "sec_facts.csv"
PROVIDER_NAMES = {"AMZN": "AWS", "GOOGL": "Google Cloud", "MSFT": "Microsoft Intelligent Cloud",
                  "ORCL": "Oracle Cloud Infrastructure", "CRWV": "CoreWeave"}


@st.cache_data(show_spinner=False)
def _compute(seg_mtime: float, facts_mtime: float, as_of: str | None, providers: tuple[str, ...], lag: int):
    seg = load_segments(SEGMENTS_PATH)
    quarters = flow_quarters(seg, as_of=as_of)
    flow_q = wide(quarters)
    flow_ttm = ttm(flow_q)
    backlog = wide(backlog_points(seg, as_of=as_of))
    panel, _ = build_panel(load_facts(FACTS_PATH), as_of=as_of)
    company = company_ttm(panel)
    capex = company.pivot_table(index="calendar_quarter", columns="ticker", values="capex")
    table = provider_table(flow_ttm, backlog, capex, list(providers), lag=lag)
    agg = aggregate_providers(table, list(providers), lag=lag)
    return seg, quarters, flow_ttm, backlog, company, table, agg


def _tile(col, label: str, value: str, help_text: str, delta: str | None = None) -> None:
    col.metric(label, value, delta, delta_color="off", help=help_text)


def render() -> None:
    if not SEGMENTS_PATH.exists():
        st.info("Segment data has not been downloaded yet.")
        return
    st.markdown("Is the CapEx from the *Capital cycle* tab matched by revenue from paying customers? "
                "Cloud sales, profit and signed future contracts, from SEC filings.")

    with st.expander("Settings"):
        providers = st.multiselect("Cloud providers", list(CLOUD_REVENUE), default=DEFAULT_PROVIDERS,
                                   format_func=lambda t: PROVIDER_NAMES[t])
        st.caption("Oracle reports cloud infrastructure separately only from 2024, and CoreWeave from 2023, so "
                   "including them shortens the aggregate's history.")
        lag = st.select_slider("CapEx lag for incremental returns (quarters)", options=[0, 2, 4, 6, 8], value=4,
                               help="New revenue this year is compared with CapEx over the twelve months ending "
                                    "this many quarters earlier, because capacity takes time to earn revenue.")
        as_of = None
        if st.toggle("Point-in-time view", key="demand_vintage"):
            as_of = st.date_input("Filings available as of", value=pd.Timestamp("2025-12-31"),
                                  key="demand_as_of").isoformat()
    if not providers:
        st.info("Choose at least one provider.")
        return

    seg, quarters, flow_ttm, backlog, company, table, agg = _compute(
        SEGMENTS_PATH.stat().st_mtime, FACTS_PATH.stat().st_mtime, as_of, tuple(sorted(providers)), lag)
    if agg.empty:
        st.warning("No quarter has twelve-month data for every selected provider.")
        return
    row = agg.iloc[-1]
    names = ", ".join(PROVIDER_NAMES[p] for p in providers)
    st.caption(f"Latest quarter with all selected providers: **{row['calendar_quarter']}** · {names} · "
               "CapEx is whole-company (see Method).")

    # ---- headline readings -------------------------------------------------
    c1, c2 = st.columns(2)
    _tile(c1, "Cloud revenue (TTM)", _fmt_bn(row["cloud_revenue"]),
          "Sum of the selected providers' cloud segment revenue.",
          _fmt_pct(row["cloud_revenue_growth"], signed=True) + " y/y")
    _tile(c2, "Cloud revenue per $ of CapEx", "n/a" if pd.isna(row["revenue_per_capex"])
          else f"${row['revenue_per_capex']:.2f}",
          "Cloud revenue ÷ the same companies' total CapEx, both over the last twelve months.")
    c3, c4 = st.columns(2)
    _tile(c3, "New revenue per $ of CapEx", "n/a" if pd.isna(row["incremental_revenue_per_capex"])
          else f"${row['incremental_revenue_per_capex']:.2f}",
          f"Growth in yearly cloud revenue ÷ CapEx over the twelve months ending {lag} quarters earlier.")
    _tile(c4, "New profit per $ of CapEx", _fmt_pct(row["incremental_income_per_capex"]),
          "Growth in yearly cloud profit ÷ the CapEx from a year earlier: a rough return on new investment. "
          f"Based on {row['profit_basis']}, the providers that report cloud profit separately.")
    c5, c6 = st.columns(2)
    _tile(c5, "Signed future contracts", _fmt_bn(row["backlog"]),
          "Money customers have already agreed to pay in future contracts but haven't been charged yet. "
          "Accountants call this 'backlog'. Whole-company figures, not cloud-only.",
          _fmt_pct(row["backlog_growth"], signed=True) + " y/y")
    _tile(c6, "Future contracts per $ of CapEx", "n/a" if pd.isna(row["backlog_coverage"])
          else f"${row['backlog_coverage']:.2f}",
          "Signed future contracts for every $1 spent on CapEx in the last twelve months.")

    x = _q(agg["calendar_quarter"])

    # ---- 1. Revenue vs CapEx -------------------------------------------------
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=x, y=agg["cloud_revenue"] / B, name="Cloud revenue", mode="lines",
                             line=dict(width=2, color=PALETTE[0]), hovertemplate="$%{y:,.0f}B"))
    fig.add_trace(go.Scatter(x=x, y=agg["capex"] / B, name="CapEx (same companies)", mode="lines",
                             line=dict(width=2, color=PALETTE[1]), hovertemplate="$%{y:,.0f}B"))
    if agg["cloud_operating_income"].notna().any():
        fig.add_trace(go.Scatter(x=x, y=agg["cloud_operating_income"] / B, name="Cloud operating income",
                                 mode="lines", line=dict(width=2, color=PALETTE[2]), hovertemplate="$%{y:,.0f}B"))
    st.plotly_chart(_layout(fig, "Cloud revenue vs CapEx", "USD B, TTM"), width="stretch", config=PLOT_CONFIG)
    st.caption("When CapEx rises above the revenue it is meant to support, the investment is running ahead of "
               "current demand. That can still make sense if customers have signed contracts for the future.")

    # ---- 2. Incremental returns ----------------------------------------------
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=x, y=agg["incremental_revenue_per_capex"], name="New revenue per $ CapEx",
                             mode="lines", line=dict(width=2, color=PALETTE[0]), hovertemplate="$%{y:.2f}"))
    if agg["incremental_income_per_capex"].notna().any():
        fig.add_trace(go.Scatter(x=x, y=agg["incremental_income_per_capex"], name="New operating profit per $ CapEx",
                                 mode="lines", line=dict(width=2, color=PALETTE[2]), hovertemplate="$%{y:.2f}"))
    st.plotly_chart(_layout(fig, f"What last year's CapEx is earning (lag {lag}q)", "$ per $ of CapEx"),
                    width="stretch", config=PLOT_CONFIG)
    st.caption("A falling line means each new dollar of investment is adding less revenue or profit than before: "
               "the core sign of diminishing returns in a capital cycle.")

    # ---- 3. Growth by provider -------------------------------------------------
    fig = go.Figure()
    shown = table[table["calendar_quarter"] >= agg["calendar_quarter"].min()]
    for ticker in providers:
        sub = shown[(shown["ticker"] == ticker) & shown["cloud_revenue_growth"].notna()]
        fig.add_trace(go.Scatter(x=_q(sub["calendar_quarter"]), y=sub["cloud_revenue_growth"],
                                 name=PROVIDER_NAMES[ticker], mode="lines", line=dict(width=2, color=COLOR[ticker]),
                                 hovertemplate="%{y:+.0%}"))
    st.plotly_chart(_layout(fig, "Cloud revenue growth by provider", "y/y, TTM", ".0%"), width="stretch",
                    config=PLOT_CONFIG)

    # ---- 4. Backlog --------------------------------------------------------------
    bl = backlog.loc[backlog.index >= agg["calendar_quarter"].min()]
    if not bl.empty:
        fig = go.Figure()
        for ticker in providers:
            name = BACKLOG.get(ticker)
            if name in bl:
                fig.add_trace(go.Bar(x=_q(bl.index), y=bl[name] / B, name=PROVIDER_NAMES[ticker].split(" ")[0]
                                     if ticker != "GOOGL" else "Alphabet",
                                     marker=dict(color=COLOR[ticker], line=dict(width=1, color="rgba(255,255,255,0.9)")),
                                     hovertemplate="$%{y:,.0f}B"))
        fig.update_layout(barmode="stack", bargap=0.25)
        st.plotly_chart(_layout(fig, "Signed future contracts by company", "USD B"), width="stretch", config=PLOT_CONFIG)
        st.caption("Money customers have agreed to pay but haven't been charged yet. These are whole-company figures "
                   "(Microsoft's include Office subscriptions, Oracle's include software support). A big share can come "
                   "from a few AI companies, and whether they pay depends on them raising money.")

    # ---- 5. Value-chain layers -----------------------------------------------------
    st.subheader("Along the value chain")
    lay = pd.DataFrame(index=flow_ttm.index)
    if "nvda_data_center_revenue" in flow_ttm:
        lay["nv"] = flow_ttm["nvda_data_center_revenue"]
    lay = lay.loc[lay.index >= agg["calendar_quarter"].min()]
    fig = go.Figure()
    if "nv" in lay:
        fig.add_trace(go.Scatter(x=_q(lay.index), y=lay["nv"] / B, name="1 · Nvidia Data Center revenue",
                                 mode="lines", line=dict(width=2, color=COLOR["NVDA"]), hovertemplate="$%{y:,.0f}B"))
    fig.add_trace(go.Scatter(x=x, y=agg["cloud_revenue"] / B, name="2 · Cloud revenue (selected)", mode="lines",
                             line=dict(width=2, color=PALETTE[0]), hovertemplate="$%{y:,.0f}B"))
    annual_openai = seg[(seg["series"] == "openai_revenue") & seg["start"].notna()]
    if not annual_openai.empty:
        latest = annual_openai.sort_values("filed").drop_duplicates(["start", "end"], keep="last")
        q_end = (latest["end"] - pd.Timedelta(days=45)).dt.to_period("Q")
        fig.add_trace(go.Scatter(x=_q(q_end), y=latest["value_usd"] / B, name="3 · OpenAI revenue (annual)",
                                 mode="markers", marker=dict(size=10, color=PALETTE[3]),
                                 hovertemplate="$%{y:,.1f}B"))
    st.plotly_chart(_layout(fig, "Revenue at each layer (not additive)", "USD B, TTM"), width="stretch",
                    config=PLOT_CONFIG)
    st.caption("Each layer's revenue is largely the next layer's cost: Nvidia's sales are the clouds' CapEx, and part "
               "of cloud revenue is AI labs' spending. Adding the lines together would count the same dollars twice. "
               "OpenAI's figure is from Microsoft's 10-K disclosure of its investee, the only audited view of "
               "the end of the chain in the filings.")

    # ---- 6. Internal use: Meta ----------------------------------------------------------
    if "meta_ads_revenue" in flow_ttm:
        meta = pd.DataFrame({"ads": flow_ttm["meta_ads_revenue"]})
        meta_capex = company[company["ticker"] == "META"].set_index("calendar_quarter")["capex"]
        meta["capex"] = meta_capex.reindex(meta.index)
        meta = meta.dropna()
        meta = meta[meta.index >= pd.Period("2021Q1")]
        if len(meta) > 4:
            growth = meta / meta.shift(4) - 1
            growth = growth.dropna()
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=_q(growth.index), y=growth["ads"], name="Ad revenue growth", mode="lines",
                                     line=dict(width=2, color=COLOR["META"]), hovertemplate="%{y:+.0%}"))
            fig.add_trace(go.Scatter(x=_q(growth.index), y=growth["capex"], name="CapEx growth", mode="lines",
                                     line=dict(width=2, color=PALETTE[1]), hovertemplate="%{y:+.0%}"))
            st.plotly_chart(_layout(fig, "Meta: AI used in-house", "y/y, TTM", ".0%", height=320), width="stretch",
                            config=PLOT_CONFIG)
            st.caption("Meta sells no cloud services: its AI spending pays off, if at all, through better ad "
                       "targeting and engagement. Ad revenue growth is the demand signal to set against its CapEx.")

    # ---- company table -----------------------------------------------------------------
    st.subheader(f"By provider · TTM to {row['calendar_quarter']}")
    latest = table[table["calendar_quarter"] == row["calendar_quarter"]]
    st.dataframe(pd.DataFrame({
        "Provider": latest["ticker"].map(PROVIDER_NAMES),
        "Cloud revenue $B": latest["cloud_revenue"] / B,
        "Growth": latest["cloud_revenue_growth"],
        "Op. margin": latest["cloud_operating_margin"],
        "Company CapEx $B": latest["capex"] / B,
        "New rev. per $ CapEx": latest["incremental_revenue_per_capex"],
        "Future contracts $B": latest["backlog"] / B,
        "Contracts per $ CapEx": latest["backlog_coverage"],
    }), hide_index=True, width="stretch", column_config={
        "Cloud revenue $B": st.column_config.NumberColumn(format="%.1f"),
        "Company CapEx $B": st.column_config.NumberColumn(format="%.1f"),
        "Future contracts $B": st.column_config.NumberColumn(format="%.0f"),
        "Growth": st.column_config.NumberColumn(format="percent"),
        "Op. margin": st.column_config.NumberColumn(format="percent"),
        "New rev. per $ CapEx": st.column_config.NumberColumn(format="$%.2f"),
        "Contracts per $ CapEx": st.column_config.NumberColumn(format="$%.2f"),
    })
    notes = [f"**{s.label}**: {s.note}" for s in SERIES if s.note]
    with st.expander("Series notes"):
        st.markdown("\n".join(f"- {n}" for n in notes))

    # ---- provenance ----------------------------------------------------------------------
    with st.expander("Data provenance: every figure and its filing"):
        options = sorted(seg["series"].unique(), key=lambda s: SERIES_BY_NAME[s].label)
        pick = st.selectbox("Series", options, format_func=lambda s: SERIES_BY_NAME[s].label,
                            index=options.index("aws_revenue") if "aws_revenue" in options else 0)
        if SERIES_BY_NAME[pick].kind == "flow":
            show = quarters[quarters["series"] == pick].copy()
        else:
            show = backlog_points(seg, as_of=as_of)
            show = show[show["series"] == pick].copy()
            show["method"] = "reported balance"
        show = show.sort_values("end", ascending=False)
        show["filing"] = [_filing_url(t, a) for t, a in zip(show["ticker"], show["accession"])]
        show["calendar_quarter"] = show["calendar_quarter"].astype(str)
        show["USD B"] = show["value_usd"] / B
        cols = [c for c in ["calendar_quarter", "start", "end", "USD B", "method", "filed", "filing"] if c in show]
        st.dataframe(show[cols], hide_index=True, width="stretch", column_config={
            "USD B": st.column_config.NumberColumn(format="%.2f"),
            "start": st.column_config.DateColumn(format="YYYY-MM-DD"),
            "end": st.column_config.DateColumn(format="YYYY-MM-DD"),
            "filed": st.column_config.DateColumn(format="YYYY-MM-DD"),
            "filing": st.column_config.LinkColumn("Filing", display_text="SEC ↗")})
        out = agg.copy()
        out["calendar_quarter"] = out["calendar_quarter"].astype(str)
        st.download_button("Download demand series (CSV)", out.to_csv(index=False), "demand_ttm.csv", "text/csv")
