"""From raw XBRL facts to a calendar-aligned quarterly panel.

Steps
1. ``select_facts``      one value per (company, concept, period): tag priority,
                         then the most recently filed value (restatements win).
                         ``as_of`` restricts to facts filed by that date, giving a
                         point-in-time vintage free of look-ahead bias.
2. ``discrete_quarters`` 10-Q cash-flow statements are year-to-date cumulative, so
                         discrete quarters are derived by differencing consecutive
                         cumulative values that share a start date. Directly reported
                         three-month values are preferred where they exist.
3. ``calendarize``       fiscal quarters are mapped to the calendar quarter that
                         contains their midpoint (e.g. Nvidia's quarter ending late
                         January covers Nov-Jan and maps to calendar Q4).
4. ``trailing_sum``      trailing-twelve-month sums over four consecutive calendar
                         quarters; any gap yields NaN rather than a partial sum.
"""
from __future__ import annotations

import pandas as pd

from .universe import DURATION_CONCEPTS, ZERO_IF_ABSENT, tags_for

QUARTER_DAYS = (80, 100)
YEAR_DAYS = (350, 380)
PANEL_KEYS = ["ticker", "calendar_quarter"]


def _days(start: pd.Series, end: pd.Series) -> pd.Series:
    return (end - start).dt.days + 1


def select_facts(facts: pd.DataFrame, as_of: str | pd.Timestamp | None = None) -> pd.DataFrame:
    """One value per (ticker, concept, start, end), with provenance."""
    df = facts.copy()
    df["start"] = pd.to_datetime(df["start"])
    df["end"] = pd.to_datetime(df["end"])
    df["filed"] = pd.to_datetime(df["filed"])
    if as_of is not None:
        df = df[df["filed"] <= pd.Timestamp(as_of)]

    pieces = []
    for concept in DURATION_CONCEPTS:
        for ticker in df["ticker"].unique():
            tags = tags_for(ticker, concept)
            sub = df[(df["ticker"] == ticker) & df["tag"].isin(tags)]
            if sub.empty:
                continue
            sub = sub.assign(concept=concept, tag_rank=sub["tag"].map({t: i for i, t in enumerate(tags)}))
            pieces.append(sub)
    if not pieces:
        return pd.DataFrame(columns=["ticker", "concept", "start", "end", "value_usd", "tag",
                                     "accession", "filed", "form"])
    chosen = pd.concat(pieces, ignore_index=True)
    # Best tag first; within a tag, latest filing (a restated figure supersedes the original).
    chosen = chosen.sort_values(["ticker", "concept", "start", "end", "tag_rank", "filed", "accession"],
                                ascending=[True, True, True, True, True, False, False])
    chosen = chosen.drop_duplicates(["ticker", "concept", "start", "end"], keep="first")
    return chosen[["ticker", "concept", "start", "end", "value_usd", "tag", "accession", "filed",
                   "form"]].reset_index(drop=True)


def discrete_quarters(selected: pd.DataFrame) -> pd.DataFrame:
    """Discrete fiscal quarters per (ticker, concept), reported or derived from YTD values."""
    if selected.empty:
        return selected.assign(method=pd.Series(dtype=str))
    df = selected.copy()
    df["days"] = _days(df["start"], df["end"])
    lo, hi = QUARTER_DAYS
    out = []
    for (ticker, concept), group in df.groupby(["ticker", "concept"], sort=False):
        by_end: dict[pd.Timestamp, dict] = {}
        # (a) directly reported three-month values
        for row in group[(group.days >= lo) & (group.days <= hi)].itertuples(index=False):
            by_end[row.end] = dict(start=row.start, end=row.end, value_usd=row.value_usd, tag=row.tag,
                                   accession=row.accession, filed=row.filed, method="reported")
        # (b) differences of consecutive cumulative values sharing a start date
        cumulative = group[(group.days >= lo) & (group.days <= YEAR_DAYS[1])]
        for _, run in cumulative.groupby("start"):
            run = run.sort_values("end")
            ends, values = list(run.end), list(run.value_usd)
            for i in range(1, len(run)):
                gap = (ends[i] - ends[i - 1]).days
                if not lo <= gap <= hi or ends[i] in by_end:
                    continue
                later = run.iloc[i]
                by_end[ends[i]] = dict(start=ends[i - 1] + pd.Timedelta(days=1), end=ends[i],
                                       value_usd=values[i] - values[i - 1], tag=later.tag,
                                       accession=later.accession, filed=later.filed,
                                       method="derived (YTD difference)")
        for record in by_end.values():
            out.append(dict(ticker=ticker, concept=concept, **record))
    result = pd.DataFrame(out)
    return result.sort_values(["ticker", "concept", "end"]).reset_index(drop=True)


def calendar_quarter(start: pd.Series, end: pd.Series) -> pd.Series:
    midpoint = start + (end - start) / 2
    return midpoint.dt.to_period("Q")


def calendarize(quarters: pd.DataFrame) -> pd.DataFrame:
    """Wide panel: one row per (ticker, calendar quarter), one column per concept.

    Optional line items (``ZERO_IF_ABSENT``) are set to zero when the company filed
    an operating cash flow figure for the quarter but did not report the item;
    the ``imputed_zero`` column lists which concepts were filled this way.
    """
    if quarters.empty:
        return pd.DataFrame(columns=PANEL_KEYS + list(DURATION_CONCEPTS))
    q = quarters.copy()
    q["calendar_quarter"] = calendar_quarter(q["start"], q["end"])
    q = q.sort_values("end").drop_duplicates(["ticker", "concept", "calendar_quarter"], keep="last")
    panel = q.pivot_table(index=PANEL_KEYS, columns="concept", values="value_usd", aggfunc="first")
    ends = q.pivot_table(index=PANEL_KEYS, values="end", aggfunc="max")
    panel = panel.reindex(columns=list(DURATION_CONCEPTS)).join(ends.rename(columns={"end": "fiscal_quarter_end"}))

    has_cash_flow = panel["operating_cash_flow"].notna()
    imputed = pd.Series("", index=panel.index, dtype=object)
    for concept in sorted(ZERO_IF_ABSENT):
        fill = has_cash_flow & panel[concept].isna()
        panel.loc[fill, concept] = 0.0
        imputed[fill] = imputed[fill] + concept + " "
    panel["imputed_zero"] = imputed.str.strip()
    return panel.reset_index()


def trailing_sum(panel: pd.DataFrame, columns: list[str], window: int = 4) -> pd.DataFrame:
    """Trailing sums over ``window`` consecutive calendar quarters, per ticker."""
    frames = []
    for ticker, group in panel.groupby("ticker", sort=False):
        group = group.set_index("calendar_quarter").sort_index()
        full = pd.period_range(group.index.min(), group.index.max(), freq="Q")
        group = group.reindex(full)
        summed = group[columns].rolling(window, min_periods=window).sum()
        summed.insert(0, "ticker", ticker)
        summed.index.name = "calendar_quarter"
        frames.append(summed.reset_index())
    if not frames:
        return pd.DataFrame(columns=PANEL_KEYS + columns)
    return pd.concat(frames, ignore_index=True)


def build_panel(facts: pd.DataFrame, as_of=None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Convenience: facts -> (calendar quarterly panel, discrete quarters with provenance)."""
    quarters = discrete_quarters(select_facts(facts, as_of=as_of))
    return calendarize(quarters), quarters
