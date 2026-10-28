"""AI Capital Cycle Monitor. Run with: streamlit run app.py"""
import sys
from pathlib import Path

# The package is normally installed via requirements.txt ("." line). This fallback
# lets the app also run from a plain checkout without installing it first.
_SRC = Path(__file__).resolve().parent / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import streamlit as st  # noqa: E402

from views import capital_cycle, demand_view, method, overview, project_model  # noqa: E402

st.set_page_config(page_title="AI Capital Cycle Monitor", layout="wide")
st.title("AI Capital Cycle Monitor")
st.caption("Independent quantitative research on the financial sustainability of AI infrastructure "
           "investment · not investment advice")

tab_overview, tab_capital, tab_demand, tab_model, tab_method = st.tabs(
    ["Overview", "Capital cycle", "Demand", "Project model", "Method & data"])
with tab_overview:
    overview.render()
with tab_capital:
    capital_cycle.render()
with tab_demand:
    demand_view.render()
with tab_model:
    project_model.render()
with tab_method:
    method.render()
