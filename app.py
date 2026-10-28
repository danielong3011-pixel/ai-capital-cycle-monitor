"""Run with: streamlit run app.py"""
import sys
from pathlib import Path

# The package is normally installed via requirements.txt ("." line). This fallback
# lets the app also run from a plain checkout without installing it first.
_SRC = Path(__file__).resolve().parent / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from dataclasses import replace
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from ai_capital_cycle.model import ProjectAssumptions, forecast, npv, break_even_growth

st.set_page_config(page_title="AI Capital Cycle Monitor", layout="wide")
st.title("AI Capital Cycle Monitor")
st.caption("Independent quantitative research | Version 0.1 — illustrative project model")
st.warning("DEMO ONLY: All inputs are hypothetical, not observed AI industry data. Results are not investment advice.")
st.markdown("Explore the cash flows required to justify an initial AI infrastructure investment. "
            "This model excludes taxes, terminal value, subsequent investment, and financing flows.")

with st.sidebar:
    st.header("Scenario assumptions")
    investment = st.slider("Initial investment (USD B)", 100, 1500, 500, 50)
    revenue = st.slider("Year 1 revenue (USD B)", 25, 300, 100, 5)
    growth = st.slider("Annual revenue growth (%)", -20, 80, 25, 5)
    margin = st.slider("Free cash flow margin (%)", 5, 70, 35, 5)
    discount = st.slider("Discount rate (%)", 5, 25, 12, 1)
    years = st.slider("Forecast horizon (years)", 2, 15, 7, 1)

params = ProjectAssumptions(investment, revenue, growth / 100, margin / 100, discount / 100, years)
result = npv(params)
root = break_even_growth(params)
a, b, c = st.columns(3)
a.metric("Project NPV (USD B)", f"{result:,.1f}")
b.metric("Break-even annual revenue growth", "Not bracketed" if root is None else f"{root:.1%}")
c.metric("Forecast years", str(years))

frame = pd.DataFrame(forecast(params))
fig = go.Figure()
fig.add_trace(go.Scatter(x=frame.year, y=frame.revenue, mode="lines+markers", name="Revenue"))
fig.add_trace(go.Scatter(x=frame.year, y=frame.free_cash_flow, mode="lines+markers", name="Free cash flow"))
fig.update_layout(title="Projected annual revenue and cash flow (USD B)", xaxis_title="Year", yaxis_title="USD B")
st.plotly_chart(fig, width="stretch")

st.subheader("Sensitivity to revenue growth and discount rate")
values = []
for rate in [0.06, 0.09, 0.12, 0.15, 0.18, 0.21]:
    values.append({"Discount rate": f"{rate:.0%}", **{
        f"{g:.0%}": round(npv(replace(params, discount_rate=rate, annual_revenue_growth=g)), 1)
        for g in [0, 0.1, 0.2, 0.3, 0.4, 0.5]}})
st.dataframe(pd.DataFrame(values).set_index("Discount rate"), width="stretch")
with st.expander("Methodology and limitations"):
    st.markdown("**NPV** = −initial investment + sum of annual FCF discounted at the assumed rate. "
                "Year 1 revenue occurs at t=1; each subsequent year grows at a constant rate. "
                "FCF equals revenue times a constant FCF margin. Break-even growth is calculated by bisection. "
                "This is a hypothetical project model, not an aggregate AI-industry estimate. "
                "Industry research will require careful treatment of overlapping revenue, AI-specific CapEx estimates, "
                "asset replacement, reporting dates and data quality.")

st.divider()
st.header("Industry aggregation · research data")
st.info("The bundled CSV contains fictional examples. Upload your own documented data to replace them. Company-level total CapEx is NOT automatically AI-specific CapEx.")
from pathlib import Path
from ai_capital_cycle.industry import annual_summary, validate_industry_data, SimulationAssumptions, simulate_npv
import numpy as np

uploaded = st.file_uploader("Upload industry observations (CSV)", type=["csv"])
try:
    source_frame = pd.read_csv(uploaded) if uploaded else pd.read_csv(Path(__file__).parent / "data" / "industry_template.csv")
    validated = validate_industry_data(source_frame)
    annual = annual_summary(source_frame)
    if validated.source.astype(str).str.contains("HYPOTHETICAL", case=False).any():
        st.warning("ILLUSTRATIVE DATA — do not interpret these as observed AI industry figures.")
    st.dataframe(annual, width="stretch", hide_index=True)
    st.plotly_chart(go.Figure(data=[
        go.Bar(x=annual.year, y=annual.reported_capex_usd_bn, name="Total reported CapEx"),
        go.Bar(x=annual.year, y=annual.estimated_ai_capex_usd_bn, name="AI-attributed CapEx (assumption-based)"),
    ]).update_layout(barmode="group", title="Capital expenditure by reporting year (USD B)"), width="stretch")
    with st.expander("View source observations and assumptions"):
        st.dataframe(validated, width="stretch", hide_index=True)
    st.download_button("Download observations CSV", source_frame.to_csv(index=False), "industry_observations.csv", "text/csv")
except (ValueError, KeyError, pd.errors.ParserError) as error:
    st.error(f"Could not validate the dataset: {error}")

st.divider()
st.header("Uncertainty · Monte Carlo scenarios")
st.caption("These are assumption-driven scenarios, NOT empirically calibrated probabilities of a market crash or investment loss.")
mc1, mc2, mc3 = st.columns(3)
with mc1:
    growth_vol = st.slider("Growth standard deviation (percentage points)", 0, 50, 15, 5)
with mc2:
    margin_vol = st.slider("FCF margin standard deviation (percentage points)", 0, 30, 10, 5)
with mc3:
    paths = st.select_slider("Simulation paths", options=[1000, 5000, 10000], value=5000)
assumptions = SimulationAssumptions(investment=investment, first_year_revenue=revenue,
    growth_mean=growth/100, growth_std=growth_vol/100, margin_mean=margin/100,
    margin_std=margin_vol/100, discount_rate=discount/100, years=years, simulations=paths)
npvs = simulate_npv(assumptions)
q05, q50, q95 = np.percentile(npvs, [5, 50, 95])
m1, m2, m3 = st.columns(3)
m1.metric("5th percentile NPV", f"${q05:,.0f}B")
m2.metric("Median NPV", f"${q50:,.0f}B")
m3.metric("95th percentile NPV", f"${q95:,.0f}B")
fig_mc = go.Figure(go.Histogram(x=npvs, nbinsx=65))
fig_mc.add_vline(x=0, line_dash="dash", annotation_text="Break-even")
fig_mc.update_layout(title="Distribution of modelled project NPVs", xaxis_title="NPV (USD B)", yaxis_title="Simulation count")
st.plotly_chart(fig_mc, width="stretch")
st.caption(f"{(npvs >= 0).mean():.1%} of simulated paths have positive NPV under the selected distributions. This is not a real-world probability estimate. Growth and margins are assumed independent and constant within each path.")
