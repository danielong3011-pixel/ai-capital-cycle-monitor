"""Who pays whom in the AI industry: a money-flow network.

``data/ai_deals.csv`` lists deals between companies, one row per flow of money from
``payer`` to ``receiver``. Deal types:

    investment     equity or similar funding
    cloud          a contract to rent computing capacity
    chips          buying (or committing to buy) chips
    manufacturing  paying a foundry to make chips

Every row carries a source link. ``amount_kind`` says how firm the amount is
(firm, approximate, up_to, commitment, reported, undisclosed). ``status`` is one of
completed, announced, filed (in an SEC filing), reported (press reports, not
confirmed by the companies) or background (a well-documented ongoing supply
relationship with no single contract amount).

Unlike the SEC-derived modules, this dataset is curated by hand from public
announcements and filings, so it is only as complete as its last update.
"""
from __future__ import annotations

from itertools import permutations

import pandas as pd

DEAL_TYPES = ("investment", "cloud", "chips", "manufacturing")
STATUSES = ("completed", "announced", "filed", "reported", "background")
AMOUNT_KINDS = ("firm", "approximate", "up_to", "commitment", "reported", "undisclosed")
COLUMNS = ["payer", "receiver", "type", "amount_usd_bn", "amount_kind", "announced", "status", "what",
           "source_url"]

# Role of each company in the chain (used for colour).
GROUPS = {
    "Nvidia": "chips", "AMD": "chips", "Broadcom": "chips", "Intel": "chips", "TSMC": "chips",
    "Cerebras": "chips",
    "Microsoft": "cloud", "Amazon": "cloud", "Google": "cloud", "Oracle": "cloud", "CoreWeave": "cloud",
    "Nebius": "cloud", "IREN": "cloud", "SpaceX": "cloud",
    "OpenAI": "ai_lab", "Anthropic": "ai_lab",
    "Meta": "ai_user",
    "SoftBank": "investor",
}
GROUP_LABELS = {"chips": "Chips", "cloud": "Cloud / compute", "ai_lab": "AI labs", "ai_user": "Uses AI in-house",
                "investor": "Investor"}


def validate_deals(frame: pd.DataFrame) -> pd.DataFrame:
    missing = set(COLUMNS) - set(frame.columns)
    if missing:
        raise ValueError(f"Missing columns: {', '.join(sorted(missing))}")
    df = frame[COLUMNS].copy()
    df["amount_usd_bn"] = pd.to_numeric(df["amount_usd_bn"], errors="raise")
    problems = []
    for i, row in df.iterrows():
        where = f"row {i + 2} ({row.payer} -> {row.receiver})"
        if row.payer == row.receiver:
            problems.append(f"{where}: payer and receiver are the same")
        for name in (row.payer, row.receiver):
            if name not in GROUPS:
                problems.append(f"{where}: unknown company '{name}' (add it to GROUPS)")
        if row.type not in DEAL_TYPES:
            problems.append(f"{where}: unknown type '{row.type}'")
        if row.status not in STATUSES:
            problems.append(f"{where}: unknown status '{row.status}'")
        if row.amount_kind not in AMOUNT_KINDS:
            problems.append(f"{where}: unknown amount_kind '{row.amount_kind}'")
        if not str(row.source_url).startswith("https://"):
            problems.append(f"{where}: source must be an https link")
        has_amount = pd.notna(row.amount_usd_bn)
        if has_amount == (row.amount_kind == "undisclosed"):
            problems.append(f"{where}: amount and amount_kind disagree")
        if has_amount and row.amount_usd_bn <= 0:
            problems.append(f"{where}: amount must be positive")
    if problems:
        raise ValueError("Invalid deals file:\n" + "\n".join(problems))
    df["announced"] = pd.to_datetime(df["announced"], errors="coerce")
    return df


def load_deals(path) -> pd.DataFrame:
    return validate_deals(pd.read_csv(path))


def filter_deals(deals: pd.DataFrame, types=DEAL_TYPES, include_background: bool = True,
                 include_reported: bool = True) -> pd.DataFrame:
    out = deals[deals["type"].isin(types)]
    if not include_background:
        out = out[out["status"] != "background"]
    if not include_reported:
        out = out[out["status"] != "reported"]
    return out.reset_index(drop=True)


def node_table(deals: pd.DataFrame) -> pd.DataFrame:
    """One row per company: distinct counterparties (size), deal counts and disclosed amounts."""
    names = sorted(set(deals["payer"]) | set(deals["receiver"]))
    rows = []
    for name in names:
        paid = deals[deals["payer"] == name]
        got = deals[deals["receiver"] == name]
        partners = set(paid["receiver"]) | set(got["payer"])
        rows.append({
            "company": name,
            "group": GROUPS.get(name, "other"),
            "connections": len(partners),
            "deals": len(paid) + len(got),
            "pays_usd_bn": paid["amount_usd_bn"].sum(min_count=1),
            "receives_usd_bn": got["amount_usd_bn"].sum(min_count=1),
        })
    return pd.DataFrame(rows).sort_values(["connections", "deals"], ascending=False).reset_index(drop=True)


def find_loops(deals: pd.DataFrame, max_length: int = 4) -> list[list[str]]:
    """Directed cycles of 2..max_length companies where money flows back to its origin.

    Each loop is returned once, rotated to start at its alphabetically first company,
    shortest loops first.
    """
    edges = set(zip(deals["payer"], deals["receiver"]))
    nodes = sorted({n for e in edges for n in e})
    loops: set[tuple[str, ...]] = set()
    for length in range(2, max_length + 1):
        for start in nodes:
            for rest in permutations([n for n in nodes if n > start], length - 1):
                path = (start, *rest)
                if all((path[i], path[(i + 1) % length]) in edges for i in range(length)):
                    loops.add(path)
    return [list(loop) for loop in sorted(loops, key=lambda p: (len(p), p))]


def deals_on_loop(deals: pd.DataFrame, loop: list[str]) -> pd.DataFrame:
    steps = set(zip(loop, loop[1:] + loop[:1]))
    mask = [(p, r) in steps for p, r in zip(deals["payer"], deals["receiver"])]
    return deals[mask]
