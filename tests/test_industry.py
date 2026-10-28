import pandas as pd
import numpy as np
import pytest
from ai_capital_cycle.industry import validate_industry_data, annual_summary, SimulationAssumptions, simulate_npv


def sample():
    return pd.DataFrame([dict(year=2025, company='A', segment='cloud', capex_usd_bn=10, operating_cash_flow_usd_bn=20, source='test', ai_capex_share=0.5, ai_capex_share_basis='assumption')])


def test_ai_capex_estimate():
    assert validate_industry_data(sample()).estimated_ai_capex_usd_bn.iloc[0] == 5


def test_annual_summary():
    s = annual_summary(sample()).iloc[0]
    assert s.capex_to_ocf == 0.5
    assert s.estimated_ai_capex_usd_bn == 5


def test_invalid_share():
    d = sample()
    d.loc[0, 'ai_capex_share'] = 1.5
    with pytest.raises(ValueError):
        validate_industry_data(d)


def test_simulation_reproducible():
    a = SimulationAssumptions(simulations=200)
    assert np.array_equal(simulate_npv(a), simulate_npv(a))


def test_simulation_deterministic_matches_analytical():
    from ai_capital_cycle.model import ProjectAssumptions, npv
    a = SimulationAssumptions(growth_std=0, margin_std=0, simulations=3)
    expected = npv(ProjectAssumptions(a.investment, a.first_year_revenue, a.growth_mean, a.margin_mean, a.discount_rate, a.years))
    assert np.allclose(simulate_npv(a), expected)
