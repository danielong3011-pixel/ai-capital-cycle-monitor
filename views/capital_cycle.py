"""Module A: AI-industry capital allocation, from SEC filings."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from ai_capital_cycle.capital import aggregate_spenders, company_ttm, latest_complete, supplier_cross_check
from ai_capital_cycle.periods import build_panel
from ai_capital_cycle.sec import load_facts
from ai_capital_cycle.universe import BY_TICKER, CAPEX_SPENDER, SUPPLIER, UNIVERSE

ROOT = Path(__file__).resolve().parents[1]
FACTS_PATH = ROOT / "data" / "sec_facts.csv"
META_PATH = ROOT / "data" / "sec_facts_meta.json"
B = 1e9

# Categorical palette (validated reference order); colour follows the company, never its rank.
PALETTE = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6"]
COLOR = {c.ticker: PALETTE[i] for i, c in enumerate(UNIVERSE)}
INK, MUTED = "#52514e", "#8a8984"
PLOT_CONFIG = {"displayModeBar": False, "scrollZoom": False}
SPENDERS = [c.ticker for c in UNIVERSE if c.role == CAPEX_SPENDER]


@st.cache_data(show_spinner=False)
def _compute(mtime: float, as_of: str | None, tickers: tuple[str, ...]):
    facts = load_facts(FACTS_PATH)
    panel, quarters = build_panel(facts, as_of=as_of)
    ttm = company_ttm(panel)
    agg = aggregate_spenders(ttm, list(tickers))
    cross = supplier_cross_check(ttm, agg)
    return panel, quarters, ttm, agg, cross


def _layout(fig: go.Figure, title: str, y_title: str, y_format: str | None = None, height: int = 360) -> go.Figure:
    fig.update_layout(
        title=dict(text=title, font=dict(size=15)), height=height, margin=dict(l=8, r=8, t=48, b=8),
        legend=dict(orientation="h", yanchor="top", y=-0.12, x=0, title=None),
        hovermode="x unified", plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
    fig.update_xaxes(showgrid=False, tickfont=dict(color=MUTED))
    fig.update_yaxes(title=y_title, gridcolor="rgba(128,128,128,0.18)", zeroline=True,
                     zerolinecolor="rgba(128,128,128,0.45)", tickfont=dict(color=MUTED), tickformat=y_format)
    return fig


def _q(series: pd.Series) -> list[str]:
    return [str(p) for p in series]


def _fmt_bn(x: float) -> str:
    return "n/a" if pd.isna(x) else f"${x / B:,.0f}B"


def _fmt_pct(x: float, signed: bool = False) -> str:
    return "n/a" if pd.isna(x) else (f"{x:+.0%}" if signed else f"{x:.0%}")


def _filing_url(ticker: str, accession: str) -> str:
    return f"https://www.sec.gov/Archives/edgar/data/{BY_TICKER[ticker].cik}/{str(accession).replace('-', '')}/"


def render() -> None:
    meta = json.loads(META_PATH.read_text()) if META_PATH.exists() else {}
    st.markdown("How much are the companies building AI compute spending, how is it paid for, and is "
                "operating cash flow keeping up? Figures are trailing-twelve-month (TTM) totals from SEC filings.")

    with st.expander("Settings"):
        chosen = st.multiselect("Companies in the aggregate", SPENDERS, default=SPENDERS,
                                format_func=lambda t: f"{BY_TICKER[t].name} ({t})")
        st.caption("CoreWeave has filed only since 2025; removing it extends the aggregate's history back to 2017.")
        use_vintage = st.toggle("Point-in-time view (only filings available on a past date)")
        as_of = None
        if use_vintage:
            as_of = st.date_input("Filings available as of", value=pd.Timestamp("2025-12-31")).isoformat()
    if not chosen:
        st.info("Choose at least one company.")
        return

    panel, quarters, ttm, agg, cross = _compute(FACTS_PATH.stat().st_mtime, as_of, tuple(sorted(chosen)))
    complete = agg[agg["complete"]]
    row = latest_complete(agg)
    if row is None:
        st.warning("No calendar quarter has TTM data for every selected company.")
        return

    vintage = f"filings available on {as_of}" if as_of else f"filings up to {meta.get('latest_filing_date', 'n/a')}"
    st.caption(f"Latest quarter with all {len(chosen)} companies reported: **{row['calendar_quarter']}** · "
               f"{vintage} · nominal USD, total company figures (not AI-only).")
    pending = agg[(agg["calendar_quarter"] > row["calendar_quarter"])]
    if not pending.empty:
        p = pending.iloc[-1]
        st.caption(f"{p['calendar_quarter']}: awaiting filings from {p['missing']}.")

    # ---- headline readings -------------------------------------------------
    c1, c2 = st.columns(2)
    c1.metric("CapEx (TTM)", _fmt_bn(row["capex"]), _fmt_pct(row["capex_yoy"], signed=True) + " y/y",
              delta_color="off", help="Cash purchases of property and equipment, summed across the selected companies.")
    c2.metric("Reinvestment rate", _fmt_pct(row["reinvestment_rate"]),
              help="CapEx ÷ operating cash flow. Above 100% means CapEx exceeds the cash the businesses generate.")
    c3, c4 = st.columns(2)
    c3.metric("Free cash flow (TTM)", _fmt_bn(row["free_cash_flow"]),
              help="Operating cash flow − CapEx.")
    c4.metric("Debt-funded share", _fmt_pct(row["debt_funding_share"]),
              help="Net debt issuance ÷ CapEx over the same twelve months.")
    c5, c6 = st.columns(2)
    c5.metric("CapEx ÷ depreciation", "n/a" if pd.isna(row["capex_to_depreciation_matched"])
              else f"{row['capex_to_depreciation_matched']:.1f}×",
              help=f"Matched sample of {int(row['depreciation_coverage'])} companies that report quarterly D&A. "
                   "Well above 1× means the asset base is growing much faster than it wears out.")
    c6.metric("Capital intensity", _fmt_pct(row["capital_intensity"]),
              help="CapEx ÷ revenue. Whole-company revenue, so retail, advertising and software dilute it.")

    # ---- 1. CapEx vs operating cash flow -----------------------------------
    x = _q(complete["calendar_quarter"])
    fig = go.Figure()
    for col, name, color in [("operating_cash_flow", "Operating cash flow", PALETTE[0]),
                             ("capex", "CapEx", PALETTE[1]),
                             ("free_cash_flow", "Free cash flow", PALETTE[2])]:
        fig.add_trace(go.Scatter(x=x, y=complete[col] / B, name=name, mode="lines", line=dict(width=2, color=color),
                                 hovertemplate="$%{y:,.0f}B"))
    st.plotly_chart(_layout(fig, "Is cash flow keeping pace with CapEx?", "USD B, TTM"), width="stretch",
                    config=PLOT_CONFIG)
    st.caption("A narrowing gap between operating cash flow and CapEx means less internally generated cash is "
               "left over after investment.")

    # ---- 2. CapEx by company (discrete quarters) ---------------------------
    recent = panel[panel["ticker"].isin(chosen) & (panel["calendar_quarter"] >= complete["calendar_quarter"].min() - 3)]
    recent = recent[recent["calendar_quarter"] <= row["calendar_quarter"]]
    fig = go.Figure()
    for ticker in chosen:
        sub = recent[recent["ticker"] == ticker]
        fig.add_trace(go.Bar(x=_q(sub["calendar_quarter"]), y=sub["capex"] / B, name=BY_TICKER[ticker].name,
                             marker=dict(color=COLOR[ticker], line=dict(width=1, color="rgba(255,255,255,0.9)")),
                             hovertemplate="$%{y:,.1f}B"))
    fig.update_layout(barmode="stack", bargap=0.25)
    st.plotly_chart(_layout(fig, "Quarterly CapEx by company", "USD B per quarter"), width="stretch",
                    config=PLOT_CONFIG)

    # ---- 3. Reinvestment rate by company -----------------------------------
    rates = ttm[ttm["ticker"].isin(chosen) & ttm["calendar_quarter"].isin(complete["calendar_quarter"])]
    fig = go.Figure()
    for ticker in chosen:
        sub = rates[rates["ticker"] == ticker]
        fig.add_trace(go.Scatter(x=_q(sub["calendar_quarter"]), y=sub["reinvestment_rate"], name=BY_TICKER[ticker].name,
                                 mode="lines", line=dict(width=2, color=COLOR[ticker]), hovertemplate="%{y:.0%}"))
    fig.add_hline(y=1, line=dict(color=INK, width=1, dash="dot"),
                  annotation=dict(text="CapEx = cash flow", font=dict(color=INK, size=11)), annotation_position="top left")
    st.plotly_chart(_layout(fig, "Reinvestment rate: CapEx ÷ operating cash flow", "TTM", ".0%"), width="stretch",
                    config=PLOT_CONFIG)

    # ---- 4. Financing ------------------------------------------------------
    fig = go.Figure()
    fig.add_trace(go.Bar(x=x, y=complete["net_debt_issuance"] / B, name="Net debt issuance",
                         marker=dict(color=PALETTE[0]), hovertemplate="$%{y:,.0f}B"))
    fig.add_trace(go.Bar(x=x, y=complete["shareholder_returns"] / B, name="Buybacks + dividends",
                         marker=dict(color=PALETTE[1]), hovertemplate="$%{y:,.0f}B"))
    fig.add_trace(go.Bar(x=x, y=complete["funding_gap"] / B, name="Funding gap",
                         marker=dict(color=PALETTE[2]), hovertemplate="$%{y:,.0f}B"))
    fig.update_layout(barmode="group", bargap=0.3, bargroupgap=0.08)
    st.plotly_chart(_layout(fig, "How is it financed?", "USD B, TTM"), width="stretch", config=PLOT_CONFIG)
    st.caption("Funding gap = CapEx + buybacks + dividends − operating cash flow. Above zero, the companies need "
               "borrowing, equity or existing cash to cover both investment and payouts. Net debt issuance can "
               "exceed the gap when companies borrow ahead of need.")

    # ---- 5. Supplier cross-check -------------------------------------------
    supplier = [c.ticker for c in UNIVERSE if c.role == SUPPLIER]
    cross = cross[cross["complete"]]
    if not cross.empty:
        fig = go.Figure()
        for ticker in supplier:
            col = f"{ticker}_revenue_to_spender_capex"
            if col in cross:
                fig.add_trace(go.Scatter(x=_q(cross["calendar_quarter"]), y=cross[col], mode="lines",
                                         name=f"{BY_TICKER[ticker].name} revenue ÷ spender CapEx",
                                         line=dict(width=2, color=COLOR[ticker]), hovertemplate="%{y:.0%}"))
        st.plotly_chart(_layout(fig, "Supplier cross-check", "TTM ratio", ".0%", height=300), width="stretch",
                        config=PLOT_CONFIG)
        st.caption("Nvidia's revenue is largely other companies' CapEx, so it is never added to the aggregate. "
                   "It includes customers outside this group, so the ratio is an upper bound on how much of the "
                   "group's CapEx flows to Nvidia, not a measured share.")

    # ---- company table -----------------------------------------------------
    st.subheader(f"Company detail · TTM to {row['calendar_quarter']}")
    latest = ttm[ttm["calendar_quarter"] == row["calendar_quarter"]].copy()
    latest = latest[latest["ticker"].isin(chosen + supplier)]
    table = pd.DataFrame({
        "Company": latest["ticker"].map(lambda t: BY_TICKER[t].name),
        "Role": latest["role"].map({CAPEX_SPENDER: "Spender", SUPPLIER: "Supplier"}),
        "CapEx $B": latest["capex"] / B,
        "CapEx y/y": latest["capex_yoy"],
        "Op. cash flow $B": latest["operating_cash_flow"] / B,
        "Reinvestment": latest["reinvestment_rate"],
        "FCF $B": latest["free_cash_flow"] / B,
        "Net debt issued $B": latest["net_debt_issuance"] / B,
        "CapEx ÷ D&A": latest["capex_to_depreciation"],
        "CapEx ÷ revenue": latest["capital_intensity"],
    })
    st.dataframe(
        table, hide_index=True, width="stretch",
        column_config={
            **{c: st.column_config.NumberColumn(format="%.1f") for c in
               ["CapEx $B", "Op. cash flow $B", "FCF $B", "Net debt issued $B"]},
            **{c: st.column_config.NumberColumn(format="percent") for c in
               ["CapEx y/y", "Reinvestment", "CapEx ÷ revenue"]},
            "CapEx ÷ D&A": st.column_config.NumberColumn(format="%.1f×"),
        })
    notes = [f"**{c.name}**: {c.note}" for c in UNIVERSE if c.note and c.ticker in chosen + supplier]
    if notes:
        with st.expander("Company notes"):
            st.markdown("\n".join(f"- {n}" for n in notes))

    # ---- provenance ----------------------------------------------------------
    with st.expander("Data provenance: every quarterly figure and its filing"):
        prov = quarters[quarters["ticker"].isin(chosen + supplier)].copy()
        prov["calendar_quarter"] = (prov["start"] + (prov["end"] - prov["start"]) / 2).dt.to_period("Q").astype(str)
        prov["filing"] = [_filing_url(t, a) for t, a in zip(prov["ticker"], prov["accession"])]
        prov["value_usd_bn"] = prov["value_usd"] / B
        show = prov.sort_values(["end", "ticker", "concept"], ascending=[False, True, True])[
            ["ticker", "concept", "calendar_quarter", "start", "end", "value_usd_bn", "method", "tag", "filed",
             "filing"]]
        concept = st.selectbox("Line item", sorted(show["concept"].unique()),
                               index=sorted(show["concept"].unique()).index("capex"))
        st.dataframe(show[show["concept"] == concept], hide_index=True, width="stretch", column_config={
            "value_usd_bn": st.column_config.NumberColumn("USD B", format="%.2f"),
            "start": st.column_config.DateColumn(format="YYYY-MM-DD"),
            "end": st.column_config.DateColumn(format="YYYY-MM-DD"),
            "filed": st.column_config.DateColumn(format="YYYY-MM-DD"),
            "filing": st.column_config.LinkColumn("Filing", display_text="SEC ↗")})
        out = agg.copy()
        out["calendar_quarter"] = out["calendar_quarter"].astype(str)
        st.download_button("Download aggregate TTM series (CSV)", out.to_csv(index=False),
                           "capital_allocation_ttm.csv", "text/csv")
