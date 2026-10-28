"""Transparent industry aggregation and scenario risk calculations."""
from dataclasses import dataclass
import numpy as np
import pandas as pd

REQUIRED = {"year", "company", "segment", "capex_usd_bn", "operating_cash_flow_usd_bn", "source", "ai_capex_share", "ai_capex_share_basis"}


def validate_industry_data(frame: pd.DataFrame) -> pd.DataFrame:
    missing = REQUIRED - set(frame.columns)
    if missing:
        raise ValueError(f"Missing columns: {', '.join(sorted(missing))}")
    df = frame.copy()
    if df.empty:
        raise ValueError("No observations")
    for col in ("year", "capex_usd_bn", "operating_cash_flow_usd_bn", "ai_capex_share"):
        df[col] = pd.to_numeric(df[col], errors="raise")
    if df[["year", "company", "segment"]].duplicated().any():
        raise ValueError("Duplicate year/company/segment rows")
    if (df.capex_usd_bn < 0).any() or ((df.ai_capex_share < 0) | (df.ai_capex_share > 1)).any():
        raise ValueError("CapEx must be nonnegative and AI share between 0 and 1")
    if df[["company", "segment", "source", "ai_capex_share_basis"]].isna().any().any():
        raise ValueError("Required metadata cannot be blank")
    df["estimated_ai_capex_usd_bn"] = df.capex_usd_bn * df.ai_capex_share
    return df


def annual_summary(frame: pd.DataFrame) -> pd.DataFrame:
    df = validate_industry_data(frame)
    summary = df.groupby("year", as_index=False).agg(
        companies=("company", "nunique"),
        reported_capex_usd_bn=("capex_usd_bn", "sum"),
        estimated_ai_capex_usd_bn=("estimated_ai_capex_usd_bn", "sum"),
        operating_cash_flow_usd_bn=("operating_cash_flow_usd_bn", "sum"),
    )
    summary["capex_to_ocf"] = summary.reported_capex_usd_bn / summary.operating_cash_flow_usd_bn.replace(0, np.nan)
    return summary


@dataclass(frozen=True)
class SimulationAssumptions:
    investment: float = 500.0
    first_year_revenue: float = 100.0
    growth_mean: float = 0.25
    growth_std: float = 0.15
    margin_mean: float = 0.35
    margin_std: float = 0.10
    discount_rate: float = 0.12
    years: int = 7
    simulations: int = 5000
    seed: int = 42


def simulate_npv(a: SimulationAssumptions) -> np.ndarray:
    """Toy scenario distribution, not calibrated real-world probabilities.

    One growth and one FCF margin per path; independently sampled, truncated normals.
    """
    if a.investment < 0 or a.first_year_revenue < 0 or a.growth_std < 0 or a.margin_std < 0:
        raise ValueError("Investment/revenue/standard deviations must be nonnegative")
    if a.discount_rate <= -1 or a.years < 1 or a.simulations < 1:
        raise ValueError("Invalid discount rate, years or simulations")
    rng = np.random.default_rng(a.seed)
    growth = np.clip(rng.normal(a.growth_mean, a.growth_std, a.simulations), -0.95, 2.0)
    margins = np.clip(rng.normal(a.margin_mean, a.margin_std, a.simulations), 0, 1)
    npvs = np.full(a.simulations, -a.investment, dtype=float)
    for year in range(1, a.years + 1):
        npvs += a.first_year_revenue * (1 + growth) ** (year - 1) * margins / (1 + a.discount_rate) ** year
    return npvs
