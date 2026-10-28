"""Runs the whole Streamlit app headlessly: every tab must render without errors."""
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[1] / "app.py"


@pytest.mark.skipif(not (APP.parent / "data" / "sec_facts.csv").exists(), reason="no SEC snapshot")
def test_app_renders_every_tab_without_errors():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(APP), default_timeout=180).run()
    assert not at.exception
    assert not at.error
    assert [t.label for t in at.tabs] == ["Overview", "Capital cycle", "Demand", "Project model", "Method & data"]
    overview = at.tabs[0]
    assert len(overview.dataframe) == 3
    assert all(not df.value.empty for df in overview.dataframe)
