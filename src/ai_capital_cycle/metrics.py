"""Accounting metrics: not AI-specific unless source data is AI-specific."""


def capital_intensity(capex: float, revenue: float) -> float | None:
    """CapEx / revenue. None if revenue is nonpositive."""
    return capex / revenue if revenue > 0 else None


def cash_flow_coverage(operating_cash_flow: float, capex: float) -> float | None:
    """Operating cash flow / CapEx. None if CapEx is nonpositive."""
    return operating_cash_flow / capex if capex > 0 else None
