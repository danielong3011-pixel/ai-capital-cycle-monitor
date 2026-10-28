"""Checks on the committed SEC snapshot: derived quarters must add back to the 10-K."""
from pathlib import Path

import pandas as pd
import pytest

from ai_capital_cycle.periods import YEAR_DAYS, discrete_quarters, select_facts
from ai_capital_cycle.sec import load_facts

SNAPSHOT = Path(__file__).resolve().parents[1] / "data" / "sec_facts.csv"
pytestmark = pytest.mark.skipif(not SNAPSHOT.exists(), reason="no SEC snapshot")


@pytest.fixture(scope="module")
def selected():
    return select_facts(load_facts(SNAPSHOT))


@pytest.mark.parametrize("concept", ["capex", "operating_cash_flow", "revenue"])
def test_quarters_sum_to_annual(selected, concept):
    sel = selected[selected.concept == concept]
    quarters = discrete_quarters(sel)
    days = (sel.end - sel.start).dt.days + 1
    annual = sel[(days >= YEAR_DAYS[0]) & (days <= YEAR_DAYS[1]) & sel.form.str.startswith("10-K")]
    checked = 0
    for year in annual.itertuples():
        q = quarters[(quarters.ticker == year.ticker) & (quarters.start >= year.start - pd.Timedelta(days=3))
                     & (quarters.end <= year.end)]
        if len(q) != 4:
            continue
        checked += 1
        # Filings round to $1M, so allow $2M of rounding across four quarters.
        assert q.value_usd.sum() == pytest.approx(year.value_usd, abs=2e6), (year.ticker, year.end)
    assert checked >= 20


def test_known_annual_capex(selected):
    """Spot checks against figures in the companies' 10-K cash-flow statements (USD billions)."""
    quarters = discrete_quarters(selected[selected.concept == "capex"])

    def total(ticker, start, end):
        q = quarters[(quarters.ticker == ticker) & (quarters.end >= start) & (quarters.end <= end)]
        assert len(q) == 4
        return q.value_usd.sum() / 1e9

    assert total("AMZN", "2024-01-01", "2024-12-31") == pytest.approx(83.0, abs=0.1)
    assert total("GOOGL", "2024-01-01", "2024-12-31") == pytest.approx(52.5, abs=0.1)
    assert total("MSFT", "2024-07-01", "2025-06-30") == pytest.approx(64.55, abs=0.1)


SEGMENTS = Path(__file__).resolve().parents[1] / "data" / "sec_segments.csv"


@pytest.mark.skipif(not SEGMENTS.exists(), reason="no segment snapshot")
def test_segment_quarters_sum_to_annual_and_known_totals():
    from ai_capital_cycle.demand import flow_quarters
    from ai_capital_cycle.segments import load_segments

    seg = load_segments(SEGMENTS)
    quarters = flow_quarters(seg)
    flows = seg[seg.start.notna() & seg.form.str.startswith("10-K")]
    annual = flows[((flows.end - flows.start).dt.days + 1).between(*YEAR_DAYS)]
    annual = annual.sort_values("filed").drop_duplicates(["series", "start", "end"], keep="last")
    checked = 0
    for year in annual.itertuples():
        q = quarters[(quarters.series == year.series) & (quarters.start >= year.start - pd.Timedelta(days=3))
                     & (quarters.end <= year.end)]
        if len(q) != 4:
            continue
        checked += 1
        assert q.value_usd.sum() == pytest.approx(year.value_usd, abs=2e6), (year.series, year.end)
    assert checked >= 30

    def cal_year(series, year):
        q = quarters[(quarters.series == series) & (quarters.calendar_quarter.astype(str).str.startswith(str(year)))]
        assert len(q) == 4
        return q.value_usd.sum() / 1e9

    assert cal_year("aws_revenue", 2024) == pytest.approx(107.6, abs=0.1)         # Amazon 10-K 2024
    assert cal_year("google_cloud_revenue", 2024) == pytest.approx(43.2, abs=0.1)  # Alphabet 10-K 2024
