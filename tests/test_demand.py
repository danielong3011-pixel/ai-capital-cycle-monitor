import numpy as np
import pandas as pd
import pytest

from ai_capital_cycle.demand import (aggregate_providers, backlog_points, flow_quarters, provider_table, ttm,
                                     wide)
from ai_capital_cycle.segments import SEGMENT_COLUMNS

REV = "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax"


def seg_rows(series, ticker, quarters, start_year=2024, filed_lag=30, accession=None):
    rows = []
    for i, value in enumerate(quarters):
        start = pd.Timestamp(year=start_year, month=1, day=1) + pd.DateOffset(months=3 * i)
        end = start + pd.DateOffset(months=3) - pd.Timedelta(days=1)
        rows.append(dict(ticker=ticker, series=series, concept=REV, dims="", start=start, end=end,
                         value_usd=float(value), accession=accession or f"{series}-{i}", form="10-Q",
                         filed=end + pd.Timedelta(days=filed_lag)))
    return rows


def backlog_rows(series, ticker, values, start_year=2024):
    rows = []
    for i, value in enumerate(values):
        end = pd.Timestamp(year=start_year, month=1, day=1) + pd.DateOffset(months=3 * (i + 1)) - pd.Timedelta(days=1)
        rows.append(dict(ticker=ticker, series=series, concept="us-gaap:RevenueRemainingPerformanceObligation",
                         dims="", start=pd.NaT, end=end, value_usd=float(value), accession=f"b{i}", form="10-Q",
                         filed=end + pd.Timedelta(days=30)))
    return rows


def test_recast_segment_value_supersedes_original():
    rows = seg_rows("aws_revenue", "AMZN", [10])
    recast = dict(rows[0], value_usd=12.0, accession="recast", filed=pd.Timestamp("2025-02-01"))
    q = flow_quarters(pd.DataFrame(rows + [recast])[SEGMENT_COLUMNS])
    assert q.value_usd.item() == 12
    assert flow_quarters(pd.DataFrame(rows + [recast])[SEGMENT_COLUMNS], as_of="2024-12-31").value_usd.item() == 10


def test_backlog_maps_fiscal_quarter_end_to_calendar_quarter():
    rows = backlog_rows("oracle_backlog", "ORCL", [5])
    rows[0]["end"] = pd.Timestamp("2025-08-31")       # Oracle fiscal Q1 (Jun-Aug) -> calendar Q3
    assert str(backlog_points(pd.DataFrame(rows)).calendar_quarter.item()) == "2025Q3"


def _setup():
    rows = (seg_rows("aws_revenue", "AMZN", [10] * 4 + [15] * 4) + seg_rows("aws_operating_income", "AMZN", [3] * 4 + [5] * 4)
            + seg_rows("google_cloud_revenue", "GOOGL", [5] * 8) + backlog_rows("amazon_backlog", "AMZN", [100] * 8))
    seg = pd.DataFrame(rows)[SEGMENT_COLUMNS]
    flow = ttm(wide(flow_quarters(seg)))
    bl = wide(backlog_points(seg))
    idx = pd.period_range("2024Q1", "2025Q4", freq="Q")
    capex = pd.DataFrame({"AMZN": [40.0] * 8, "GOOGL": [20.0] * 8}, index=idx)
    return provider_table(flow, bl, capex, ["AMZN", "GOOGL"], lag=4)


def test_provider_measures():
    t = _setup().set_index(["ticker", "calendar_quarter"])
    row = t.loc[("AMZN", pd.Period("2025Q4"))]
    assert row.cloud_revenue == 60 and row.cloud_revenue_growth == pytest.approx(0.5)
    assert row.cloud_operating_margin == pytest.approx(20 / 60)
    assert row.incremental_revenue_per_capex == pytest.approx(20 / 40)      # lagged CapEx (2024Q4) = 40
    assert row.incremental_income_per_capex == pytest.approx(8 / 40)
    assert row.backlog_coverage == pytest.approx(100 / 40)


def test_aggregate_requires_every_provider_and_marks_partial_income_nan():
    t = _setup()
    agg = aggregate_providers(t, ["AMZN", "GOOGL"]).set_index("calendar_quarter")
    row = agg.loc[pd.Period("2025Q4")]
    assert row.cloud_revenue == 80 and row.capex == 60
    assert np.isnan(row.cloud_operating_income)   # Google Cloud income not supplied here
    assert np.isnan(row.backlog)                  # nor Google backlog
    assert pd.Period("2024Q3") not in agg.index   # no TTM revenue yet
