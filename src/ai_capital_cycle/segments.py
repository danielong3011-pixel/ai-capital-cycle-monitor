"""Segment, product and backlog series extracted from XBRL instance documents.

Each ``Series`` names one economic quantity (e.g. AWS revenue) and the XBRL
concepts and dimension members that identify it in a company's filings. Matching
ignores namespace prefixes, so it survives the yearly taxonomy-version changes in
prefixes, and ignores the ``ConsolidationItemsAxis=OperatingSegmentsMember``
qualifier that some filers add to segment facts.

Value-chain layers (see demand.py): figures are only ever summed within a layer.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from .xbrl_instance import parse_instance

SUPPLIER_LAYER = "1 supplier"
COMPUTE_LAYER = "2 compute provider"
AI_APP_LAYER = "3 AI model / application"
INTERNAL_LAYER = "internal AI use"

REVENUE = ("Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax",
           "RevenueFromContractWithCustomerIncludingAssessedTax")
OPERATING_INCOME = ("OperatingIncomeLoss",)
BACKLOG = ("RevenueRemainingPerformanceObligation",)
IGNORED_DIMS = frozenset({"ConsolidationItemsAxis=OperatingSegmentsMember"})

SEGMENT_COLUMNS = ["ticker", "series", "concept", "dims", "start", "end", "value_usd", "accession", "form",
                   "filed"]


@dataclass(frozen=True)
class Series:
    name: str
    ticker: str
    label: str
    kind: str                     # "flow" (over a period) or "instant" (balance at a date)
    measure: str                  # "revenue", "operating_income", "backlog"
    layer: str
    concepts: tuple[str, ...]
    dims: tuple[frozenset, ...] = field(default=(frozenset(),))   # accepted dimension sets
    note: str = ""


def _d(*pairs: str) -> frozenset:
    return frozenset(pairs)


SERIES: tuple[Series, ...] = (
    # Layer 2: compute providers
    Series("aws_revenue", "AMZN", "AWS revenue", "flow", "revenue", COMPUTE_LAYER, REVENUE,
           (_d("StatementBusinessSegmentsAxis=AmazonWebServicesSegmentMember"),)),
    Series("aws_operating_income", "AMZN", "AWS operating income", "flow", "operating_income", COMPUTE_LAYER,
           OPERATING_INCOME, (_d("StatementBusinessSegmentsAxis=AmazonWebServicesSegmentMember"),)),
    Series("google_cloud_revenue", "GOOGL", "Google Cloud revenue", "flow", "revenue", COMPUTE_LAYER, REVENUE,
           (_d("StatementBusinessSegmentsAxis=GoogleCloudMember"),)),
    Series("google_cloud_operating_income", "GOOGL", "Google Cloud operating income", "flow", "operating_income",
           COMPUTE_LAYER, OPERATING_INCOME, (_d("StatementBusinessSegmentsAxis=GoogleCloudMember"),)),
    Series("google_cloud_backlog", "GOOGL", "Google Cloud backlog", "instant", "backlog", COMPUTE_LAYER, BACKLOG,
           (_d("StatementBusinessSegmentsAxis=GoogleCloudMember"),)),
    Series("msft_intelligent_cloud_revenue", "MSFT", "Microsoft Intelligent Cloud revenue", "flow", "revenue",
           COMPUTE_LAYER, REVENUE, (_d("StatementBusinessSegmentsAxis=IntelligentCloudMember"),),
           "Segment includes server software (SQL Server, Windows Server) as well as Azure."),
    Series("msft_intelligent_cloud_operating_income", "MSFT", "Microsoft Intelligent Cloud operating income", "flow",
           "operating_income", COMPUTE_LAYER, OPERATING_INCOME,
           (_d("StatementBusinessSegmentsAxis=IntelligentCloudMember"),)),
    Series("msft_microsoft_cloud_revenue", "MSFT", "Microsoft Cloud revenue", "flow", "revenue", COMPUTE_LAYER,
           REVENUE, (_d("ProductsOrServicesSecondaryCategorizationAxis=MicrosoftCloudMember"),),
           "Microsoft's own measure: Azure plus commercial Microsoft 365, Dynamics 365, LinkedIn commercial and more."),
    Series("msft_commercial_backlog", "MSFT", "Microsoft commercial backlog", "instant", "backlog", COMPUTE_LAYER,
           BACKLOG, (_d("MajorCustomersAxis=CommercialCustomersMember"),),
           "All commercial contracts, including Microsoft 365, not only Azure."),
    Series("oci_revenue", "ORCL", "Oracle Cloud Infrastructure revenue", "flow", "revenue", COMPUTE_LAYER, REVENUE,
           (_d("ProductOrServiceAxis=CloudInfrastructureMember"),)),
    Series("oracle_backlog", "ORCL", "Oracle backlog", "instant", "backlog", COMPUTE_LAYER, BACKLOG, (frozenset(),),
           "Total company remaining performance obligations, including software support."),
    Series("coreweave_revenue", "CRWV", "CoreWeave revenue", "flow", "revenue", COMPUTE_LAYER, REVENUE,
           (frozenset(),)),
    Series("coreweave_backlog", "CRWV", "CoreWeave backlog", "instant", "backlog", COMPUTE_LAYER, BACKLOG,
           (frozenset(),)),
    # Layer 1: supplier
    Series("nvda_data_center_revenue", "NVDA", "Nvidia Data Center revenue", "flow", "revenue", SUPPLIER_LAYER,
           REVENUE, (_d("ProductOrServiceAxis=DataCenterMember"),)),
    Series("nvda_hyperscale_revenue", "NVDA", "Nvidia revenue from hyperscalers", "flow", "revenue", SUPPLIER_LAYER,
           REVENUE, (_d("ProductOrServiceAxis=HyperscaleMember"),), "Disclosed only in recent filings."),
    # Layer 3: AI model companies (audited glimpses only)
    Series("openai_revenue", "MSFT", "OpenAI revenue (Microsoft equity-method disclosure)", "flow", "revenue",
           AI_APP_LAYER, REVENUE,
           (_d("ScheduleOfEquityMethodInvestmentEquityMethodInvesteeNameAxis=OpenAIGlobalLlcMember"),),
           "Summarised financial information of OpenAI Global LLC in Microsoft's 10-K; annual only. The investee's "
           "reporting period may not match Microsoft's fiscal year."),
    # Internal use: AI improves the owner's own products
    Series("meta_ads_revenue", "META", "Meta advertising revenue", "flow", "revenue", INTERNAL_LAYER, REVENUE,
           (_d("ProductOrServiceAxis=AdvertisingMember", "StatementBusinessSegmentsAxis=FamilyOfAppsMember"),
            _d("ProductOrServiceAxis=AdvertisingMember"))),
    Series("meta_family_of_apps_operating_income", "META", "Meta Family of Apps operating income", "flow",
           "operating_income", INTERNAL_LAYER, OPERATING_INCOME,
           (_d("StatementBusinessSegmentsAxis=FamilyOfAppsMember"),)),
)

SERIES_BY_NAME = {s.name: s for s in SERIES}


def _local_dims(dims: str) -> frozenset:
    """'us-gaap:StatementBusinessSegmentsAxis=amzn:AwsMember' -> {'StatementBusinessSegmentsAxis=AwsMember'}."""
    if not dims:
        return frozenset()
    pairs = []
    for pair in dims.split(";"):
        axis, _, member = pair.partition("=")
        pairs.append(f"{axis.rsplit(':', 1)[-1]}={member.rsplit(':', 1)[-1]}")
    return frozenset(pairs) - IGNORED_DIMS


def extract_series(instance: pd.DataFrame, ticker: str) -> pd.DataFrame:
    """Rows of a parsed instance that match one of the company's series specs."""
    specs = [s for s in SERIES if s.ticker == ticker]
    if instance.empty or not specs:
        return pd.DataFrame(columns=SEGMENT_COLUMNS[:7])
    df = instance[instance["unit"].str.lower().str.contains("usd")].copy()
    df["local_concept"] = df["concept"].str.rsplit(":", n=1).str[-1]
    df["local_dims"] = df["dims"].map(_local_dims)
    out = []
    for spec in specs:
        hit = df["local_concept"].isin(spec.concepts) & df["local_dims"].isin(spec.dims)
        hit &= df["start"].isna() if spec.kind == "instant" else df["start"].notna()
        sub = df[hit]
        if not sub.empty:
            out.append(sub.assign(series=spec.name, ticker=ticker, value_usd=sub["value"]))
    if not out:
        return pd.DataFrame(columns=SEGMENT_COLUMNS[:7])
    rows = pd.concat(out, ignore_index=True)
    return rows[["ticker", "series", "concept", "dims", "start", "end", "value_usd"]].drop_duplicates()


def extract_from_filing(xml_bytes: bytes, ticker: str, accession: str, form: str, filed: str) -> pd.DataFrame:
    rows = extract_series(parse_instance(xml_bytes), ticker)
    return rows.assign(accession=accession, form=form, filed=filed)[SEGMENT_COLUMNS]


def load_segments(path) -> pd.DataFrame:
    frame = pd.read_csv(path, dtype={"ticker": str, "series": str, "concept": str, "dims": str,
                                     "accession": str, "form": str}, keep_default_na=False,
                        na_values={"start": [""], "value_usd": [""]})
    for col in ("start", "end", "filed"):
        frame[col] = pd.to_datetime(frame[col])
    return frame[SEGMENT_COLUMNS]
