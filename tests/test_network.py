from pathlib import Path

import pandas as pd
import pytest

from ai_capital_cycle.network import COLUMNS, filter_deals, find_loops, load_deals, node_table, validate_deals

DEALS = Path(__file__).resolve().parents[1] / "data" / "ai_deals.csv"


def deal(payer, receiver, type_="cloud", amount=1.0, kind="firm", status="announced"):
    return dict(payer=payer, receiver=receiver, type=type_, amount_usd_bn=amount, amount_kind=kind,
                announced="2025-01-01", status=status, what="x", source_url="https://example.com")


def test_committed_deals_file_is_valid():
    deals = load_deals(DEALS)
    assert len(deals) >= 30
    assert deals.source_url.str.startswith("https://").all()


def test_validation_catches_bad_rows():
    bad = pd.DataFrame([deal("Nvidia", "Nvidia"), deal("Nvidia", "Acme"), deal("OpenAI", "Oracle", kind="undisclosed")])
    with pytest.raises(ValueError) as err:
        validate_deals(bad[COLUMNS])
    message = str(err.value)
    assert "same" in message and "unknown company 'Acme'" in message and "disagree" in message


def test_node_size_counts_distinct_counterparties():
    d = validate_deals(pd.DataFrame([deal("Nvidia", "OpenAI", "investment"), deal("OpenAI", "Nvidia", "chips"),
                                     deal("OpenAI", "Oracle")])[COLUMNS])
    nodes = node_table(d).set_index("company")
    assert nodes.loc["OpenAI", "connections"] == 2 and nodes.loc["OpenAI", "deals"] == 3
    assert nodes.loc["Nvidia", "connections"] == 1


def test_loops_found_once_and_shortest_first():
    d = validate_deals(pd.DataFrame([deal("Nvidia", "OpenAI"), deal("OpenAI", "Nvidia"), deal("OpenAI", "Oracle"),
                                     deal("Oracle", "Nvidia")])[COLUMNS])
    assert find_loops(d) == [["Nvidia", "OpenAI"], ["Nvidia", "OpenAI", "Oracle"]]


def test_filters():
    d = validate_deals(pd.DataFrame([deal("Meta", "Oracle", status="reported"),
                                     deal("Microsoft", "Nvidia", "chips", None, "undisclosed", "background")])[COLUMNS])
    assert filter_deals(d, include_reported=False).payer.tolist() == ["Microsoft"]
    assert filter_deals(d, include_background=False).payer.tolist() == ["Meta"]
    assert filter_deals(d, types=["chips"]).payer.tolist() == ["Microsoft"]
