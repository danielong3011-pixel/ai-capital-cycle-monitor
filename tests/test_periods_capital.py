import numpy as np
import pandas as pd
import pytest

from ai_capital_cycle.capital import aggregate_spenders, company_ttm, supplier_cross_check
from ai_capital_cycle.periods import (build_panel, calendar_quarter, calendarize, discrete_quarters,
                                      select_facts, trailing_sum)
from ai_capital_cycle.sec import flatten_companyfacts
from ai_capital_cycle.universe import BY_TICKER

CAPEX = "PaymentsToAcquirePropertyPlantAndEquipment"
OCF = "NetCashProvidedByUsedInOperatingActivities"


def fact(ticker, tag, start, end, value, filed, accession="a", form="10-Q"):
    return dict(ticker=ticker, cik=1, tag=tag, start=start, end=end, value_usd=float(value),
                accession=accession, form=form, fiscal_year=None, fiscal_period=None, filed=filed)


def ytd_year(ticker, tag, year, quarterly, filed_year=None, start_month=1):
    """Cumulative YTD facts (as in 10-Q cash-flow statements) for one fiscal year."""
    filed_year = filed_year or year
    start = pd.Timestamp(year=year, month=start_month, day=1)
    rows, total = [], 0.0
    for q, value in enumerate(quarterly, start=1):
        total += value
        end = (start + pd.DateOffset(months=3 * q) - pd.Timedelta(days=1)).date().isoformat()
        filed = (pd.Timestamp(end) + pd.Timedelta(days=30)).date().isoformat()
        rows.append(fact(ticker, tag, start.date().isoformat(), end, total, filed,
                         accession=f"{ticker}-{year}-{q}", form="10-K" if q == 4 else "10-Q"))
    return rows


def test_ytd_differencing_recovers_discrete_quarters():
    facts = pd.DataFrame(ytd_year("MSFT", CAPEX, 2024, [10, 20, 30, 40]))
    q = discrete_quarters(select_facts(facts))
    assert list(q.value_usd) == [10, 20, 30, 40]
    assert q.method.iloc[0] == "reported" and q.method.iloc[1].startswith("derived")


def test_missing_quarter_derived_from_annual_less_other_three():
    rows = [fact("MSFT", CAPEX, s, e, v, "2024-12-31", f"q{i}", form) for i, (s, e, v, form) in enumerate([
        ("2024-01-01", "2024-03-31", 10, "10-Q"), ("2024-04-01", "2024-06-30", 20, "10-Q"),
        ("2024-10-01", "2024-12-31", 40, "10-Q"), ("2024-01-01", "2024-12-31", 100, "10-K")])]
    q = discrete_quarters(select_facts(pd.DataFrame(rows))).set_index("end")
    q3 = q.loc[pd.Timestamp("2024-09-30")]
    assert q3.value_usd == 30 and q3.start == pd.Timestamp("2024-07-01")
    assert q3.method == "derived (annual less other quarters)"


def test_annual_amount_mistagged_as_quarter_is_ignored():
    rows = ytd_year("ORCL", "Revenues", 2024, [10, 10, 10, 10])
    rows.append(fact("ORCL", "Revenues", "2024-10-01", "2024-12-31", 40, "2025-06-30", "bad", "10-K"))
    q = discrete_quarters(select_facts(pd.DataFrame(rows)))
    assert list(q.value_usd) == [10, 10, 10, 10]


def test_ttm_figures_in_10q_not_treated_as_fiscal_years():
    rows = [fact("AMZN", CAPEX, s, e, v, "2024-12-31", f"q{i}") for i, (s, e, v) in enumerate([
        ("2024-01-01", "2024-03-31", 10), ("2024-04-01", "2024-06-30", 20), ("2024-10-01", "2024-12-31", 40),
        ("2024-01-01", "2024-12-31", 999)])]          # 12-month figure from a 10-Q
    q = discrete_quarters(select_facts(pd.DataFrame(rows)))
    assert pd.Timestamp("2024-09-30") not in set(q.end)


def test_reported_three_month_value_preferred_over_derived():
    rows = ytd_year("MSFT", CAPEX, 2024, [10, 20, 30, 40])
    rows.append(fact("MSFT", CAPEX, "2024-04-01", "2024-06-30", 21, "2024-07-30", "direct"))
    q = discrete_quarters(select_facts(pd.DataFrame(rows)))
    assert q.loc[q.end == "2024-06-30", "value_usd"].item() == 21


def test_restatement_supersedes_and_as_of_gives_vintage():
    rows = [fact("MSFT", CAPEX, "2024-01-01", "2024-03-31", 10, "2024-04-30", "orig"),
            fact("MSFT", CAPEX, "2024-01-01", "2024-03-31", 12, "2025-04-30", "restated")]
    facts = pd.DataFrame(rows)
    assert select_facts(facts).value_usd.item() == 12
    assert select_facts(facts, as_of="2024-12-31").value_usd.item() == 10


def test_tag_priority_and_company_override():
    rows = [fact("AMZN", CAPEX, "2024-01-01", "2024-03-31", 5, "2024-04-30"),
            fact("AMZN", "PaymentsToAcquireProductiveAssets", "2024-01-01", "2024-03-31", 9, "2024-04-30"),
            fact("MSFT", CAPEX, "2024-01-01", "2024-03-31", 5, "2024-04-30"),
            fact("MSFT", "PaymentsToAcquireProductiveAssets", "2024-01-01", "2024-03-31", 9, "2024-04-30")]
    sel = select_facts(pd.DataFrame(rows)).set_index("ticker")
    assert sel.loc["AMZN", "value_usd"] == 9   # override prefers ProductiveAssets
    assert sel.loc["MSFT", "value_usd"] == 5


def test_calendar_quarter_uses_midpoint():
    start = pd.to_datetime(pd.Series(["2025-10-27", "2026-06-01", "2026-07-01"]))
    end = pd.to_datetime(pd.Series(["2026-01-25", "2026-08-31", "2026-09-30"]))
    assert [str(p) for p in calendar_quarter(start, end)] == ["2025Q4", "2026Q3", "2026Q3"]


def test_trailing_sum_requires_four_consecutive_quarters():
    panel = pd.DataFrame({"ticker": "X", "calendar_quarter": pd.PeriodIndex(
        ["2024Q1", "2024Q2", "2024Q4", "2025Q1", "2025Q2", "2025Q3"], freq="Q"),
        "capex": [1.0, 1, 1, 1, 1, 1]})
    out = trailing_sum(panel, ["capex"]).set_index("calendar_quarter")["capex"]
    assert np.isnan(out[pd.Period("2025Q1")])        # 2024Q3 missing
    assert out[pd.Period("2025Q3")] == 4


def test_optional_items_zero_filled_only_when_cash_flow_reported():
    rows = ytd_year("MSFT", OCF, 2024, [50, 50, 50, 50]) + ytd_year("MSFT", CAPEX, 2024, [10, 10, 10, 10])
    panel, _ = build_panel(pd.DataFrame(rows))
    assert (panel.debt_issued == 0).all()
    assert panel.imputed_zero.str.contains("debt_issued").all()
    assert panel.revenue.isna().all()                 # core concept never imputed


def _two_company_facts(include_second_latest=True):
    rows = []
    for year in (2023, 2024):
        rows += ytd_year("MSFT", OCF, year, [50] * 4) + ytd_year("MSFT", CAPEX, year, [10 * (year - 2022)] * 4)
        quarters = 4 if (year == 2023 or include_second_latest) else 3
        rows += ytd_year("META", OCF, year, [40] * quarters) + ytd_year("META", CAPEX, year, [20] * quarters)
    rows += ytd_year("NVDA", "Revenues", 2023, [30] * 4) + ytd_year("NVDA", "Revenues", 2024, [60] * 4)
    return pd.DataFrame(rows)


def test_aggregate_sums_spenders_and_computes_ratios_from_sums():
    panel, _ = build_panel(_two_company_facts())
    agg = aggregate_spenders(company_ttm(panel)).set_index("calendar_quarter")
    row = agg.loc[pd.Period("2024Q4")]
    assert row.capex == 4 * 20 + 4 * 20 and row.operating_cash_flow == 4 * 50 + 4 * 40
    assert row.reinvestment_rate == pytest.approx(160 / 360)
    assert row.free_cash_flow == 200
    assert row.capex_yoy == pytest.approx(160 / 120 - 1)
    assert row.complete


def test_supplier_revenue_never_added_to_spender_capex():
    panel, _ = build_panel(_two_company_facts())
    ttm = company_ttm(panel)
    agg = aggregate_spenders(ttm)
    assert "NVDA" not in set(ttm[ttm.role == "capex_spender"].ticker)
    check = supplier_cross_check(ttm, agg).set_index("calendar_quarter").loc[pd.Period("2024Q4")]
    assert check.NVDA_revenue == 240 and check.capex == 160
    assert check.NVDA_revenue_to_spender_capex == pytest.approx(1.5)


def test_incomplete_quarter_flagged_and_excluded_from_growth():
    panel, _ = build_panel(_two_company_facts(include_second_latest=False))
    agg = aggregate_spenders(company_ttm(panel)).set_index("calendar_quarter")
    last = agg.loc[pd.Period("2024Q4")]
    assert not last.complete and last.missing == "META"
    assert np.isnan(last.capex_yoy)


def test_flatten_companyfacts_filters_forms_and_instants():
    payload = {"facts": {"us-gaap": {CAPEX: {"units": {"USD": [
        {"start": "2024-01-01", "end": "2024-03-31", "val": 5, "accn": "x", "fy": 2024, "fp": "Q1",
         "form": "10-Q", "filed": "2024-04-30"},
        {"start": "2024-01-01", "end": "2024-03-31", "val": 5, "accn": "y", "fy": 2024, "fp": "Q1",
         "form": "8-K", "filed": "2024-04-25"},
        {"end": "2024-03-31", "val": 7, "accn": "z", "form": "10-Q", "filed": "2024-04-30"}]}}}}}
    flat = flatten_companyfacts(payload, BY_TICKER["MSFT"])
    assert len(flat) == 1 and flat.accession.item() == "x"
