"""Interactive 3D 'who pays whom' map (part of the Demand tab)."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from ai_capital_cycle.network import DEAL_TYPES, filter_deals, find_loops, load_deals, node_table
from views import map3d

ROOT = Path(__file__).resolve().parents[1]
DEALS_PATH = ROOT / "data" / "ai_deals.csv"
TYPE_LABELS = {k: v[1] for k, v in map3d.TYPE_STYLE.items()}
MAP_HEIGHT = 520


def render() -> None:
    st.subheader("Who pays whom")
    st.markdown("Each line is money moving from one company to another: an investment, a cloud contract or a "
                "chip purchase. The moving dots show which way it flows. Bigger balls have more connections.")
    deals_all = load_deals(DEALS_PATH)

    with st.expander("Map settings"):
        types = st.multiselect("Show these kinds of deal", list(DEAL_TYPES), default=list(DEAL_TYPES),
                               format_func=TYPE_LABELS.get, key="net_types")
        background = st.toggle("Include ongoing supply relationships (no single deal)", value=True, key="net_bg",
                               help="E.g. Microsoft buying Nvidia chips: certain, but not one announced contract.")
        reported = st.toggle("Include deals known only from press reports", value=True, key="net_rep")
    deals = filter_deals(deals_all, types or DEAL_TYPES, background, reported)
    if deals.empty:
        st.info("No deals match these settings.")
        return

    theme = getattr(getattr(st.context, "theme", None), "type", None)
    html = "<style>body{margin:0}</style>" + map3d.build(deals, height=MAP_HEIGHT, theme=theme)
    frame_height = MAP_HEIGHT + 300
    if hasattr(st, "iframe"):          # Streamlit's replacement for components.html
        st.iframe(html, height=frame_height)
    else:
        import streamlit.components.v1 as components
        components.html(html, height=frame_height, scrolling=True)

    nodes = node_table(deals)
    loops = find_loops(deals, max_length=3)
    c1, c2 = st.columns(2)
    c1.metric("Companies on the map", len(nodes))
    c2.metric("Money loops (2–3 companies)", len(loops),
              help="Chains where money flows out and comes back, e.g. Nvidia invests in OpenAI, which buys "
                   "Nvidia chips. Pick one under the map to light it up.")
    st.caption("Why loops matter: if a supplier funds its own customers, part of its sales is paid for with its "
               "own money. That isn't necessarily wrong, but it means some demand depends on the investment cycle "
               "continuing rather than on end customers.")

    with st.expander("All deals and sources"):
        company = st.selectbox("Company", ["All"] + nodes["company"].tolist(), key="net_company")
        table = deals if company == "All" else deals[(deals.payer == company) | (deals.receiver == company)]
        st.dataframe(pd.DataFrame({
            "From": table["payer"], "To": table["receiver"], "Kind": table["type"].map(TYPE_LABELS),
            "Amount": [map3d.amount_text(r) for r in table.itertuples()],
            "When": table["announced"].dt.strftime("%b %Y").fillna(""),
            "Status": table["status"].map(map3d.STATUS_LABELS), "What": table["what"], "Source": table["source_url"],
        }), hide_index=True, width="stretch",
            column_config={"Source": st.column_config.LinkColumn(display_text="source ↗")})
        st.caption(f"Hand-collected from company announcements, SEC filings and press reports; "
                   f"{len(deals_all)} deals, latest {deals_all['announced'].max():%d %b %Y}. "
                   "Unlike the rest of the app it is not updated automatically. Amounts are what was announced "
                   "(often 'up to' or multi-year commitments), not money already paid.")
