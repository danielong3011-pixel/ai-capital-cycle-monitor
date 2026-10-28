"""Module A: AI-industry capital allocation.

All figures are trailing-twelve-month (TTM) sums of calendar-aligned quarters, in
nominal USD. Company figures are *total* reported amounts: reported CapEx is not
the same as AI CapEx (Amazon's includes retail logistics, for example).

Definitions (TTM)
    capex                       cash purchases of property, plant and equipment
    free_cash_flow              operating cash flow - capex
    fcf_after_finance_leases    free cash flow - finance-lease principal repayments
    reinvestment_rate           capex / operating cash flow
    capital_intensity           capex / revenue
    capex_to_depreciation       capex / depreciation & amortisation
                                (>1: asset base expanding; ~1: replacement only)
    shareholder_returns         buybacks + dividends
    funding_gap                 capex + shareholder returns - operating cash flow
                                (>0: must be met from borrowing, equity or cash on hand)
    net_debt_issuance           debt issued - debt repaid + net short-term borrowing
    debt_funding_share          net debt issuance / capex
    capex_yoy                   capex / capex four quarters earlier - 1

Aggregates sum spender companies only, and only for calendar quarters in which
*every* company in the chosen set has a TTM value (``complete``); otherwise a
change in coverage could masquerade as a change in spending.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .periods import trailing_sum
from .universe import CAPEX_SPENDER, SUPPLIER, UNIVERSE

FLOW_COLUMNS = ["capex", "operating_cash_flow", "revenue", "depreciation_amortization",
                "finance_lease_principal", "finance_lease_additions", "debt_issued", "debt_repaid",
                "short_term_debt_net", "buybacks", "dividends"]


def _ratio(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    """Ratio that is NaN (not +/-inf) when the denominator is zero or negative."""
    return numerator / denominator.where(denominator > 0)


def add_ratios(frame: pd.DataFrame) -> pd.DataFrame:
    df = frame.copy()
    df["free_cash_flow"] = df["operating_cash_flow"] - df["capex"]
    df["fcf_after_finance_leases"] = df["free_cash_flow"] - df["finance_lease_principal"]
    df["shareholder_returns"] = df["buybacks"] + df["dividends"]
    df["funding_gap"] = df["capex"] + df["shareholder_returns"] - df["operating_cash_flow"]
    df["net_debt_issuance"] = df["debt_issued"] - df["debt_repaid"] + df["short_term_debt_net"]
    df["reinvestment_rate"] = _ratio(df["capex"], df["operating_cash_flow"])
    df["capital_intensity"] = _ratio(df["capex"], df["revenue"])
    df["capex_to_depreciation"] = _ratio(df["capex"], df["depreciation_amortization"])
    df["debt_funding_share"] = _ratio(df["net_debt_issuance"], df["capex"])
    return df


def _yoy(frame: pd.DataFrame, column: str, by: str | None) -> pd.Series:
    """Growth versus four calendar quarters earlier (exact quarter match, no positional shift)."""
    keys = [by] if by else []
    prior = frame[keys + ["calendar_quarter", column]].copy()
    prior["calendar_quarter"] = prior["calendar_quarter"] + 4
    merged = frame[keys + ["calendar_quarter"]].merge(prior, on=keys + ["calendar_quarter"], how="left")
    current = pd.Series(frame[column].to_numpy(dtype=float), index=frame.index)
    previous = pd.Series(merged[column].to_numpy(dtype=float), index=frame.index)
    return _ratio(current, previous) - 1


def company_ttm(panel: pd.DataFrame) -> pd.DataFrame:
    """TTM flows and ratios per company and calendar quarter."""
    ttm = trailing_sum(panel, FLOW_COLUMNS)
    ttm = add_ratios(ttm)
    ttm["capex_yoy"] = _yoy(ttm, "capex", by="ticker")
    roles = {c.ticker: c.role for c in UNIVERSE}
    ttm.insert(1, "role", ttm["ticker"].map(roles))
    return ttm


def aggregate_spenders(ttm: pd.DataFrame, tickers: list[str] | None = None) -> pd.DataFrame:
    """Sum of spender companies per calendar quarter, with a coverage flag.

    Ratios are recomputed from the summed flows (a capex-weighted aggregate), not
    averaged across companies.
    """
    spenders = ttm[ttm["role"] == CAPEX_SPENDER]
    if tickers is not None:
        spenders = spenders[spenders["ticker"].isin(tickers)]
    expected = sorted(spenders["ticker"].unique()) if tickers is None else sorted(tickers)
    valid = spenders.dropna(subset=["capex", "operating_cash_flow"])
    grouped = valid.groupby("calendar_quarter")
    agg = grouped[FLOW_COLUMNS].sum(min_count=1)
    agg["companies"] = grouped["ticker"].nunique()
    agg["missing"] = grouped["ticker"].agg(lambda s: ", ".join(sorted(set(expected) - set(s))))
    # Revenue / D&A sums are only meaningful if every included company reported them.
    for column in ["revenue", "depreciation_amortization"]:
        agg[column] = agg[column].where(grouped[column].count() == agg["companies"])
    agg["complete"] = agg["companies"] == len(expected)
    # Matched-sample CapEx / D&A: both sides restricted to companies reporting D&A,
    # because some filers (e.g. Microsoft) do not tag quarterly D&A consistently.
    matched = valid.dropna(subset=["depreciation_amortization"]).groupby("calendar_quarter")
    agg["capex_to_depreciation_matched"] = _ratio(matched["capex"].sum(),
                                                  matched["depreciation_amortization"].sum())
    agg["depreciation_coverage"] = matched["ticker"].nunique()
    agg = agg.reset_index()
    agg = add_ratios(agg)
    agg["capex_yoy"] = _yoy(agg.assign(capex=agg["capex"].where(agg["complete"])), "capex", by=None)
    shares = valid.pivot_table(index="calendar_quarter", columns="ticker", values="capex", aggfunc="sum")
    shares = shares.div(shares.sum(axis=1), axis=0)
    agg["capex_hhi"] = agg["calendar_quarter"].map((shares.fillna(0) ** 2).sum(axis=1))
    return agg.sort_values("calendar_quarter").reset_index(drop=True)


def supplier_cross_check(ttm: pd.DataFrame, aggregate: pd.DataFrame) -> pd.DataFrame:
    """Supplier revenue relative to spender CapEx: a cross-check, never a sum.

    Supplier revenue includes sales to customers outside the spender set and
    non-data-centre products, so the ratio is an upper-bound indicator of how much
    of spenders' CapEx accrues to the supplier, not a measured share.
    """
    suppliers = ttm[ttm["role"] == SUPPLIER]
    wide = suppliers.pivot_table(index="calendar_quarter", columns="ticker", values="revenue", aggfunc="first")
    wide.columns = [f"{c}_revenue" for c in wide.columns]
    out = aggregate[["calendar_quarter", "capex", "complete"]].merge(wide.reset_index(), on="calendar_quarter",
                                                                       how="inner")
    for column in [c for c in out.columns if c.endswith("_revenue")]:
        out[column.replace("_revenue", "_revenue_to_spender_capex")] = _ratio(out[column], out["capex"])
    return out


def latest_complete(aggregate: pd.DataFrame) -> pd.Series | None:
    done = aggregate[aggregate["complete"]]
    return None if done.empty else done.iloc[-1]


def summary_signals(aggregate: pd.DataFrame) -> dict[str, float]:
    """Headline readings for the most recent quarter with full coverage."""
    row = latest_complete(aggregate)
    if row is None:
        return {}
    keys = ["capex", "operating_cash_flow", "free_cash_flow", "reinvestment_rate", "capex_yoy",
            "capital_intensity", "capex_to_depreciation_matched", "funding_gap", "net_debt_issuance",
            "debt_funding_share", "capex_hhi"]
    return {k: float(row[k]) if pd.notna(row[k]) else np.nan for k in keys} | {
        "calendar_quarter": str(row["calendar_quarter"])}
