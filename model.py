"""Transparent illustrative project-level financial calculations.

All cash flows and capital are in the same currency units (e.g. USD billions).
This is a *project* model, not an industry estimate. No terminal value is assumed.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class ProjectAssumptions:
    initial_investment: float
    first_year_revenue: float
    annual_revenue_growth: float
    free_cash_flow_margin: float
    discount_rate: float
    years: int = 7

    def validate(self) -> None:
        if self.initial_investment < 0 or self.first_year_revenue < 0:
            raise ValueError("Investment and revenue must be nonnegative")
        if self.annual_revenue_growth <= -1:
            raise ValueError("Revenue growth must exceed -100%")
        if not 0 <= self.free_cash_flow_margin <= 1:
            raise ValueError("FCF margin must be between 0 and 1")
        if self.discount_rate <= -1:
            raise ValueError("Discount rate must exceed -100%")
        if not isinstance(self.years, int) or self.years < 1:
            raise ValueError("Years must be a positive integer")


def forecast(assumptions: ProjectAssumptions) -> list[dict]:
    """Year-end revenue, free cash flow and present value; first year at t=1."""
    assumptions.validate()
    rows = []
    for year in range(1, assumptions.years + 1):
        revenue = assumptions.first_year_revenue * (1 + assumptions.annual_revenue_growth) ** (year - 1)
        fcf = revenue * assumptions.free_cash_flow_margin
        rows.append({"year": year, "revenue": revenue, "free_cash_flow": fcf,
                     "present_value": fcf / (1 + assumptions.discount_rate) ** year})
    return rows


def npv(assumptions: ProjectAssumptions) -> float:
    """NPV of initial investment and forecast FCF, excluding terminal value."""
    return -assumptions.initial_investment + sum(row["present_value"] for row in forecast(assumptions))


def break_even_growth(assumptions: ProjectAssumptions, low: float = -0.99,
                      high: float = 5.0, tolerance: float = 1e-8) -> float | None:
    """Bisection root for growth making NPV zero, or None if not bracketed.

    With a one-year horizon, growth does not affect NPV; return None.
    """
    assumptions.validate()
    if assumptions.years == 1 or assumptions.first_year_revenue == 0 or assumptions.free_cash_flow_margin == 0:
        return None
    from dataclasses import replace
    def value(g: float) -> float:
        return npv(replace(assumptions, annual_revenue_growth=g))
    left, right = value(low), value(high)
    if left * right > 0:
        return None
    for _ in range(120):
        mid = (low + high) / 2
        val = value(mid)
        if abs(val) < tolerance or high - low < tolerance:
            return mid
        if val * left <= 0:
            high = mid
        else:
            low, left = mid, val
    return (low + high) / 2
