"""Company universe and the XBRL concepts used to measure it.

Each company is assigned a *role* in the AI value chain. Roles matter because
the same dollar appears more than once along the chain: an Nvidia GPU sale is
Nvidia's revenue and, simultaneously, a hyperscaler's capital expenditure.
Aggregates therefore sum *within* a role, never across roles.

    capex_spender  builds and operates AI compute capacity (hyperscalers, neoclouds)
    supplier       sells the hardware that spenders capitalise (used as a cross-check)
"""
from __future__ import annotations

from dataclasses import dataclass

CAPEX_SPENDER = "capex_spender"
SUPPLIER = "supplier"


@dataclass(frozen=True)
class Company:
    ticker: str
    cik: int
    name: str
    role: str
    note: str = ""

    @property
    def cik10(self) -> str:
        return f"{self.cik:010d}"


UNIVERSE: tuple[Company, ...] = (
    Company("MSFT", 789019, "Microsoft", CAPEX_SPENDER,
            "Fiscal year ends June. Large finance-lease data-centre additions are excluded from cash CapEx."),
    Company("AMZN", 1018724, "Amazon", CAPEX_SPENDER,
            "CapEx includes retail logistics, not only AWS. Tagged PaymentsToAcquireProductiveAssets."),
    Company("GOOGL", 1652044, "Alphabet", CAPEX_SPENDER),
    Company("META", 1326801, "Meta Platforms", CAPEX_SPENDER,
            "Off-balance-sheet joint-venture data centres are not captured in reported CapEx."),
    Company("ORCL", 1341439, "Oracle", CAPEX_SPENDER, "Fiscal year ends May."),
    Company("CRWV", 1769628, "CoreWeave", CAPEX_SPENDER, "Public filer since 2025; short history."),
    Company("NVDA", 1045810, "Nvidia", SUPPLIER,
            "Fiscal year ends late January. Revenue is largely other firms' CapEx: never added to the spender aggregate."),
)

BY_TICKER = {c.ticker: c for c in UNIVERSE}


# Each concept maps to an ordered list of us-gaap tags. Companies use different
# tags for the same line item, and change tags over time. For any given period the
# first tag in the list that has a value is used (see periods.select_facts); the
# chosen tag is kept in the output so every figure is auditable.
DURATION_CONCEPTS: dict[str, tuple[str, ...]] = {
    "capex": ("PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets"),
    "operating_cash_flow": ("NetCashProvidedByUsedInOperatingActivities",),
    "revenue": ("Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax"),
    "depreciation_amortization": (
        "DepreciationDepletionAndAmortization",
        "DepreciationAmortizationAndAccretionNet",
        "DepreciationAndAmortization",
        "Depreciation",
    ),
    "finance_lease_principal": ("FinanceLeasePrincipalPayments",),
    "finance_lease_additions": ("RightOfUseAssetObtainedInExchangeForFinanceLeaseLiability",),
    "debt_issued": (
        "ProceedsFromIssuanceOfLongTermDebt",
        "ProceedsFromIssuanceOfSeniorLongTermDebt",
        "ProceedsFromDebtNetOfIssuanceCosts",
        "ProceedsFromIssuanceOfDebt",
    ),
    "debt_repaid": ("RepaymentsOfLongTermDebt", "RepaymentsOfDebt", "RepaymentsOfSeniorDebt"),
    "short_term_debt_net": (
        "ProceedsFromRepaymentsOfShortTermDebtMaturingInThreeMonthsOrLess",
        "ProceedsFromRepaymentsOfCommercialPaper",
    ),
    "buybacks": ("PaymentsForRepurchaseOfCommonStock",),
    "dividends": ("PaymentsOfDividends", "PaymentsOfDividendsCommonStock"),
}

# Per-company tag priority overrides, where a company's own filings show the
# generic order would pick a superseded or narrower tag.
TAG_OVERRIDES: dict[tuple[str, str], tuple[str, ...]] = {
    ("AMZN", "capex"): ("PaymentsToAcquireProductiveAssets", "PaymentsToAcquirePropertyPlantAndEquipment"),
    ("NVDA", "capex"): ("PaymentsToAcquireProductiveAssets", "PaymentsToAcquirePropertyPlantAndEquipment"),
}

# Concepts for which a missing value in a period where the company otherwise filed
# a cash flow statement is treated as zero (the line item simply did not occur,
# e.g. a quarter with no bond issuance). Core concepts are never imputed.
ZERO_IF_ABSENT = frozenset({
    "finance_lease_principal", "finance_lease_additions", "debt_issued", "debt_repaid",
    "short_term_debt_net", "buybacks", "dividends",
})


def tags_for(ticker: str, concept: str) -> tuple[str, ...]:
    return TAG_OVERRIDES.get((ticker, concept), DURATION_CONCEPTS[concept])


def all_tags() -> set[str]:
    tags = {t for ts in DURATION_CONCEPTS.values() for t in ts}
    tags.update(t for ts in TAG_OVERRIDES.values() for t in ts)
    return tags
