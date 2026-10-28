import pytest
from ai_capital_cycle.model import ProjectAssumptions, npv, forecast, break_even_growth
from ai_capital_cycle.metrics import capital_intensity, cash_flow_coverage


def test_simple_npv():
    p = ProjectAssumptions(100, 60, 0, 1, 0, 2)
    assert npv(p) == pytest.approx(20)


def test_discounting():
    p = ProjectAssumptions(0, 110, 0, 1, .1, 1)
    assert npv(p) == pytest.approx(100)


def test_break_even():
    p = ProjectAssumptions(100, 40, 0.2, 1, 0, 2)
    g = break_even_growth(p)
    assert g is not None
    assert npv(ProjectAssumptions(100, 40, g, 1, 0, 2)) == pytest.approx(0, abs=1e-5)


def test_invalid():
    with pytest.raises(ValueError):
        forecast(ProjectAssumptions(100, 50, 0.2, 1.2, 0.1, 5))


def test_metrics():
    assert capital_intensity(20, 100) == .2
    assert cash_flow_coverage(100, 50) == 2
    assert capital_intensity(10, 0) is None
