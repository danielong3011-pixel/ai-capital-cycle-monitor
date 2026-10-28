"""Module B: is AI infrastructure spending backed by customer demand?

Value-chain layers (never summed across layers, because one layer's revenue is the
next layer's cost or CapEx):

    1 supplier                 Nvidia Data Center revenue    = compute providers' CapEx
    2 compute provider         AWS, Google Cloud, Microsoft Intelligent Cloud, OCI,
                               CoreWeave revenue              = partly AI labs' costs
    3 AI model / application   OpenAI revenue                 = spending by final customers
    internal AI use            Meta advertising: AI improves the owner's own product

Measures (TTM = trailing twelve months, calendar-aligned)
    cloud_revenue                   sum over the selected providers
    cloud_revenue_growth            vs four quarters earlier
    cloud_operating_margin          for providers that report segment operating income
    revenue_per_capex               cloud revenue / the same companies' total CapEx
    incremental_revenue_per_capex   (cloud revenue - cloud revenue a year earlier)
                                    / CapEx over the twelve months ending ``lag`` quarters earlier
    incremental_income_per_capex    same with segment operating income: a rough pre-tax
                                    incremental return on the capital spent
    backlog_coverage                backlog / TTM CapEx: contracted future revenue per $ of CapEx

CapEx is whole-company (Amazon's includes retail), so these ratios understate the
return on cloud CapEx alone: read their *direction* over time, not their level.
"""
from __future__ import annotations

import pandas as pd

from .periods import calendar_quarter, discrete_quarters
from .segments import SERIES_BY_NAME

CLOUD_REVENUE = {
    "AMZN": "aws_revenue",
    "GOOGL": "google_cloud_revenue",
    "MSFT": "msft_intelligent_cloud_revenue",
    "ORCL": "oci_revenue",
    "CRWV": "coreweave_revenue",
}
CLOUD_OPERATING_INCOME = {
    "AMZN": "aws_operating_income",
    "GOOGL": "google_cloud_operating_income",
    "MSFT": "msft_intelligent_cloud_operating_income",
}
BACKLOG = {
    "AMZN": "amazon_backlog",
    "GOOGL": "google_backlog",
    "MSFT": "msft_commercial_backlog",
    "ORCL": "oracle_backlog",
    "CRWV": "coreweave_backlog",
}
DEFAULT_PROVIDERS = ["AMZN", "GOOGL", "MSFT"]


def _latest_filed(frame: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    """One row per key: the most recently filed value (restatements and recasts win)."""
    ordered = frame.sort_values(keys + ["filed", "accession"], ascending=[True] * len(keys) + [False, False])
    return ordered.drop_duplicates(keys, keep="first")


def flow_quarters(segments: pd.DataFrame, as_of=None) -> pd.DataFrame:
    """Discrete calendar quarters for every flow series, with provenance."""
    seg = segments if as_of is None else segments[segments["filed"] <= pd.Timestamp(as_of)]
    flows = seg[seg["start"].notna()]
    chosen = _latest_filed(flows, ["ticker", "series", "start", "end"])
    chosen = chosen.rename(columns={"series": "concept", "concept": "tag"})
    quarters = discrete_quarters(chosen[["ticker", "concept", "start", "end", "value_usd", "tag", "accession",
                                         "filed", "form"]])
    if quarters.empty:
        return quarters.assign(calendar_quarter=pd.Series(dtype="period[Q-DEC]"))
    quarters = quarters.rename(columns={"concept": "series"})
    quarters["calendar_quarter"] = calendar_quarter(quarters["start"], quarters["end"])
    return quarters.sort_values("end").drop_duplicates(["series", "calendar_quarter"], keep="last")


def backlog_points(segments: pd.DataFrame, as_of=None) -> pd.DataFrame:
    """Backlog balances, each mapped to the calendar quarter its fiscal quarter mostly covers."""
    seg = segments if as_of is None else segments[segments["filed"] <= pd.Timestamp(as_of)]
    points = _latest_filed(seg[seg["start"].isna()], ["ticker", "series", "end"]).copy()
    # A balance at a fiscal quarter-end belongs to the same calendar quarter as that
    # fiscal quarter's flows (whose midpoint is ~45 days earlier).
    points["calendar_quarter"] = (points["end"] - pd.Timedelta(days=45)).dt.to_period("Q")
    return points.sort_values("end").drop_duplicates(["series", "calendar_quarter"], keep="last")


def wide(frame: pd.DataFrame) -> pd.DataFrame:
    """calendar_quarter x series table of values, on a complete quarterly index."""
    if frame.empty:
        return pd.DataFrame()
    table = frame.pivot_table(index="calendar_quarter", columns="series", values="value_usd", aggfunc="first")
    full = pd.period_range(table.index.min(), table.index.max(), freq="Q")
    return table.reindex(full).rename_axis("calendar_quarter")


def ttm(quarterly: pd.DataFrame) -> pd.DataFrame:
    """Trailing four-quarter sums; NaN unless all four quarters are present."""
    return quarterly.rolling(4, min_periods=4).sum()


def _ratio(a: pd.Series, b: pd.Series) -> pd.Series:
    return a / b.where(b > 0)


def provider_table(flow_ttm: pd.DataFrame, backlog: pd.DataFrame, capex_ttm: pd.DataFrame,
                   providers: list[str], lag: int = 4) -> pd.DataFrame:
    """Long table: one row per (provider, calendar quarter) with demand measures."""
    rows = []
    for ticker in providers:
        rev = flow_ttm.get(CLOUD_REVENUE[ticker])
        if rev is None:
            continue
        index = rev.index.union(capex_ttm.index) if not capex_ttm.empty else rev.index
        frame = pd.DataFrame(index=index)
        frame["cloud_revenue"] = rev.reindex(index)
        oi_name = CLOUD_OPERATING_INCOME.get(ticker)
        frame["cloud_operating_income"] = flow_ttm[oi_name].reindex(index) if oi_name in flow_ttm else float("nan")
        bl_name = BACKLOG.get(ticker)
        frame["backlog"] = backlog[bl_name].reindex(index) if bl_name in backlog else float("nan")
        frame["capex"] = capex_ttm[ticker].reindex(index) if ticker in capex_ttm else float("nan")
        frame["ticker"] = ticker
        rows.append(frame.rename_axis("calendar_quarter").reset_index())
    if not rows:
        return pd.DataFrame()
    out = pd.concat(rows, ignore_index=True)
    return add_demand_ratios(out, by="ticker", lag=lag)


def add_demand_ratios(frame: pd.DataFrame, by: str | None, lag: int = 4) -> pd.DataFrame:
    df = frame.sort_values(([by] if by else []) + ["calendar_quarter"]).reset_index(drop=True)

    def shifted(column: str, periods: int) -> pd.Series:
        # Exact quarter matching (not positional) so gaps never misalign periods.
        keys = ([by] if by else []) + ["calendar_quarter"]
        prior = df[keys + [column]].copy()
        prior["calendar_quarter"] = prior["calendar_quarter"] + periods
        merged = df[keys].merge(prior, on=keys, how="left")
        return pd.Series(merged[column].to_numpy(dtype=float), index=df.index)

    df["cloud_revenue_growth"] = _ratio(df["cloud_revenue"], shifted("cloud_revenue", 4)) - 1
    df["cloud_operating_margin"] = _ratio(df["cloud_operating_income"], df["cloud_revenue"])
    df["revenue_per_capex"] = _ratio(df["cloud_revenue"], df["capex"])
    lagged_capex = shifted("capex", lag)
    df["incremental_revenue"] = df["cloud_revenue"] - shifted("cloud_revenue", 4)
    df["incremental_operating_income"] = df["cloud_operating_income"] - shifted("cloud_operating_income", 4)
    df["incremental_revenue_per_capex"] = _ratio(df["incremental_revenue"], lagged_capex)
    df["incremental_income_per_capex"] = _ratio(df["incremental_operating_income"], lagged_capex)
    df["backlog_growth"] = _ratio(df["backlog"], shifted("backlog", 4)) - 1
    df["backlog_coverage"] = _ratio(df["backlog"], df["capex"])
    return df


def aggregate_providers(table: pd.DataFrame, providers: list[str], lag: int = 4) -> pd.DataFrame:
    """Sum across providers per quarter, only where every provider has revenue and CapEx.

    Operating income and backlog are summed over the providers that report them; the
    ``income_coverage`` and ``backlog_coverage_n`` columns say how many did.
    """
    if table.empty:
        return pd.DataFrame()
    sub = table[table["ticker"].isin(providers)]
    valid = sub.dropna(subset=["cloud_revenue", "capex"])
    g = valid.groupby("calendar_quarter")
    agg = g[["cloud_revenue", "capex"]].sum()
    agg["providers"] = g["ticker"].nunique()
    agg["complete"] = agg["providers"] == len(providers)
    with_income = valid.dropna(subset=["cloud_operating_income"]).groupby("calendar_quarter")
    agg["cloud_operating_income"] = with_income["cloud_operating_income"].sum()
    agg["income_coverage"] = with_income["ticker"].nunique()
    agg["income_revenue"] = with_income["cloud_revenue"].sum()
    with_backlog = valid.dropna(subset=["backlog"]).groupby("calendar_quarter")
    agg["backlog"] = with_backlog["backlog"].sum()
    agg["backlog_coverage_n"] = with_backlog["ticker"].nunique()
    agg = agg[agg["complete"]].reset_index()
    # Operating income and backlog only count when every provider reports them; otherwise
    # their growth would reflect changes in coverage rather than in the business.
    agg.loc[agg["income_coverage"] != len(providers), "cloud_operating_income"] = float("nan")
    agg.loc[agg["backlog_coverage_n"] != len(providers), "backlog"] = float("nan")
    out = add_demand_ratios(agg, by=None, lag=lag)
    return out.drop(columns=["income_revenue"])


def layer_view(flow_ttm: pd.DataFrame, cloud_aggregate: pd.DataFrame) -> pd.DataFrame:
    """Side-by-side TTM revenue at each layer of the chain. NOT additive across columns."""
    out = pd.DataFrame(index=flow_ttm.index)
    out["layer1_nvidia_data_center"] = flow_ttm.get("nvda_data_center_revenue")
    if not cloud_aggregate.empty:
        out["layer2_cloud_revenue"] = cloud_aggregate.set_index("calendar_quarter")["cloud_revenue"]
    return out.rename_axis("calendar_quarter").reset_index()


def series_label(name: str) -> str:
    return SERIES_BY_NAME[name].label
