import pandas as pd

from ai_capital_cycle.xbrl_instance import instance_filename, parse_instance, recent_periodic_filings

INSTANCE = b"""<?xml version="1.0" encoding="utf-8"?>
<xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance" xmlns:xbrldi="http://xbrl.org/2006/xbrldi"
  xmlns:us-gaap="http://fasb.org/us-gaap/2025" xmlns:amzn="http://www.amazon.com/20250930"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <xbrli:context id="q3"><xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">1018724</xbrli:identifier></xbrli:entity>
    <xbrli:period><xbrli:startDate>2025-07-01</xbrli:startDate><xbrli:endDate>2025-09-30</xbrli:endDate></xbrli:period></xbrli:context>
  <xbrli:context id="q3_aws"><xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">1018724</xbrli:identifier>
    <xbrli:segment><xbrldi:explicitMember dimension="us-gaap:StatementBusinessSegmentsAxis">amzn:AmazonWebServicesSegmentMember</xbrldi:explicitMember></xbrli:segment></xbrli:entity>
    <xbrli:period><xbrli:startDate>2025-07-01</xbrli:startDate><xbrli:endDate>2025-09-30</xbrli:endDate></xbrli:period></xbrli:context>
  <xbrli:context id="i"><xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">1018724</xbrli:identifier></xbrli:entity>
    <xbrli:period><xbrli:instant>2025-09-30</xbrli:instant></xbrli:period></xbrli:context>
  <xbrli:unit id="usd"><xbrli:measure>iso4217:USD</xbrli:measure></xbrli:unit>
  <us-gaap:Revenues contextRef="q3" unitRef="usd" decimals="-6">180169000000</us-gaap:Revenues>
  <us-gaap:Revenues contextRef="q3_aws" unitRef="usd" decimals="-6">33006000000</us-gaap:Revenues>
  <us-gaap:RevenueRemainingPerformanceObligation contextRef="i" unitRef="usd" decimals="-9">200000000000</us-gaap:RevenueRemainingPerformanceObligation>
  <us-gaap:Revenues contextRef="i" unitRef="usd" xsi:nil="true"/>
</xbrli:xbrl>"""


def test_parse_instance_dimensions_and_periods():
    df = parse_instance(INSTANCE)
    aws = df[df.dims != ""].iloc[0]
    assert aws.concept == "us-gaap:Revenues" and aws.value == 33006000000
    assert aws.dims == "us-gaap:StatementBusinessSegmentsAxis=amzn:AmazonWebServicesSegmentMember"
    rpo = df[df.concept == "us-gaap:RevenueRemainingPerformanceObligation"].iloc[0]
    assert pd.isna(rpo.start) and rpo.end == pd.Timestamp("2025-09-30")
    assert len(df) == 3


def test_instance_filename_and_filing_list():
    assert instance_filename("amzn-20250930.htm") == "amzn-20250930_htm.xml"
    subs = {"filings": {"recent": {"accessionNumber": ["a", "b", "c"], "form": ["10-Q", "8-K", "10-K"],
                                   "filingDate": ["2025-10-31", "2025-10-30", "2018-02-01"],
                                   "reportDate": ["2025-09-30", "", "2017-12-31"],
                                   "primaryDocument": ["x.htm", "y.htm", "z.htm"], "isInlineXBRL": [1, 0, 0]}}}
    assert list(recent_periodic_filings(subs).accessionNumber) == ["a"]


def test_extract_series_matches_ignoring_prefixes_and_consolidation_axis():
    from ai_capital_cycle.segments import extract_series
    inst = pd.DataFrame([
        dict(concept="us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax", value=24.77e9,
             start=pd.Timestamp("2026-04-01"), end=pd.Timestamp("2026-06-30"), unit="usd",
             dims="us-gaap:StatementBusinessSegmentsAxis=goog:GoogleCloudMember", context="a"),
        dict(concept="us-gaap:OperatingIncomeLoss", value=8.81e9, start=pd.Timestamp("2026-04-01"),
             end=pd.Timestamp("2026-06-30"), unit="usd", context="b",
             dims="srt:ConsolidationItemsAxis=us-gaap:OperatingSegmentsMember;"
                  "us-gaap:StatementBusinessSegmentsAxis=goog:GoogleCloudMember"),
        dict(concept="us-gaap:RevenueRemainingPerformanceObligation", value=513.9e9, start=pd.NaT,
             end=pd.Timestamp("2026-06-30"), unit="usd", context="c",
             dims="us-gaap:StatementBusinessSegmentsAxis=goog:GoogleCloudMember"),
        dict(concept="us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax", value=1e9,
             start=pd.Timestamp("2026-04-01"), end=pd.Timestamp("2026-06-30"), unit="usd", context="d",
             dims="srt:StatementGeographicalAxis=country:US;us-gaap:StatementBusinessSegmentsAxis=goog:GoogleCloudMember"),
    ])
    out = extract_series(inst, "GOOGL").set_index("series")
    assert out.loc["google_cloud_revenue", "value_usd"] == 24.77e9      # geographic split excluded
    assert out.loc["google_cloud_operating_income", "value_usd"] == 8.81e9
    assert out.loc["google_cloud_backlog", "value_usd"] == 513.9e9
    assert len(out) == 3


def test_wildcard_axis_match():
    from ai_capital_cycle.segments import _matches, _d
    dims = frozenset({"RevenueRemainingPerformanceObligationExpectedTimingOfSatisfactionStartDateAxis=2026-01-01"})
    assert _matches(dims, (_d("RevenueRemainingPerformanceObligationExpectedTimingOfSatisfactionStartDateAxis=*"),))
    assert not _matches(dims, (frozenset(),))
    assert _matches(frozenset(), (frozenset(),))
