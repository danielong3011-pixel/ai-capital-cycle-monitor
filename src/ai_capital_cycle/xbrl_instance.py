"""Read dimensional facts (segments, products, customers) from XBRL instance documents.

SEC's companyfacts API only carries facts *without* dimensions, so segment revenue
(AWS, Google Cloud, Microsoft's Intelligent Cloud...) is absent from it. Those facts
live in each filing's XBRL instance document. For inline-XBRL filings SEC publishes
the extracted instance alongside the filing as ``<primary document>_htm.xml``.

Only the standard library is used for parsing so the module runs anywhere.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET

import pandas as pd

XBRLI = "http://www.xbrl.org/2003/instance"
XBRLDI = "http://xbrl.org/2006/xbrldi"
ARCHIVE = "https://www.sec.gov/Archives/edgar/data/{cik}/{acc}"
SUBMISSIONS = "https://data.sec.gov/submissions/CIK{cik10}.json"
INSTANCE_COLUMNS = ["concept", "value", "start", "end", "dims", "unit", "context"]


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _prefixed(tag: str, prefixes: dict[str, str]) -> str:
    namespace, _, local = tag[1:].partition("}")
    return f"{prefixes.get(namespace, namespace)}:{local}"


def _qname(text: str) -> str:
    """'us-gaap:StatementBusinessSegmentsAxis' -> unchanged; strips whitespace."""
    return text.strip()


def parse_instance(xml_bytes: bytes) -> pd.DataFrame:
    """All numeric facts in an XBRL instance with their period and dimensions.

    ``dims`` is a canonical string ``axis=member;axis=member`` (sorted), empty for
    facts without dimensions. Instant facts have ``start`` equal to NaT.
    """
    prefixes: dict[str, str] = {}
    for _, (prefix, uri) in ET.iterparse(_bytes_io(xml_bytes), events=["start-ns"]):
        prefixes.setdefault(uri, prefix)
    root = ET.fromstring(xml_bytes)

    contexts: dict[str, tuple] = {}
    for ctx in root.iter(f"{{{XBRLI}}}context"):
        period = ctx.find(f"{{{XBRLI}}}period")
        instant = period.find(f"{{{XBRLI}}}instant")
        if instant is not None:
            start, end = None, instant.text.strip()
        else:
            start = period.find(f"{{{XBRLI}}}startDate").text.strip()
            end = period.find(f"{{{XBRLI}}}endDate").text.strip()
        members = []
        for member in ctx.iter(f"{{{XBRLDI}}}explicitMember"):
            members.append(f"{_qname(member.get('dimension'))}={_qname(member.text)}")
        for member in ctx.iter(f"{{{XBRLDI}}}typedMember"):
            value = "".join(member.itertext()).strip()
            members.append(f"{_qname(member.get('dimension'))}={value}")
        contexts[ctx.get("id")] = (start, end, ";".join(sorted(members)))

    rows = []
    for element in root:
        context_ref = element.get("contextRef")
        if context_ref is None or context_ref not in contexts or element.get("unitRef") is None:
            continue
        text = (element.text or "").strip()
        if not text or element.get("{http://www.w3.org/2001/XMLSchema-instance}nil") == "true":
            continue
        try:
            value = float(text)
        except ValueError:
            continue
        start, end, dims = contexts[context_ref]
        rows.append((_prefixed(element.tag, prefixes), value, start, end, dims, element.get("unitRef"), context_ref))
    frame = pd.DataFrame(rows, columns=INSTANCE_COLUMNS).drop_duplicates(
        ["concept", "start", "end", "dims", "unit", "value"])
    frame["start"] = pd.to_datetime(frame["start"])
    frame["end"] = pd.to_datetime(frame["end"])
    return frame.reset_index(drop=True)


def _bytes_io(data: bytes):
    import io

    return io.BytesIO(data)


def instance_filename(primary_document: str) -> str:
    """'msft-20250930.htm' -> 'msft-20250930_htm.xml' (SEC's extracted inline-XBRL instance)."""
    return re.sub(r"\.htm$", "_htm.xml", primary_document)


FILING_FIELDS = ["accessionNumber", "form", "filingDate", "reportDate", "primaryDocument", "isInlineXBRL"]
SUBMISSIONS_PAGE = "https://data.sec.gov/submissions/{name}"


def _filing_block(block: dict) -> pd.DataFrame:
    return pd.DataFrame({k: block.get(k, []) for k in FILING_FIELDS})


def recent_periodic_filings(submissions: dict, forms=("10-K", "10-Q"), since: str = "2019-01-01",
                            extra_pages: list[dict] | None = None) -> pd.DataFrame:
    """Periodic filings from a company's submissions JSON.

    The main JSON lists only the most recent ~1,000 filings of all types; older ones
    are in additional pages (``filings.files``), passed here as ``extra_pages``.
    """
    blocks = [_filing_block(submissions.get("filings", {}).get("recent", {}))]
    blocks += [_filing_block(page) for page in (extra_pages or [])]
    frame = pd.concat(blocks, ignore_index=True).drop_duplicates("accessionNumber")
    frame = frame[frame["form"].isin(forms) & (frame["filingDate"] >= since)]
    return frame.reset_index(drop=True)


def instance_url(cik: int, accession: str, primary_document: str) -> str:
    return f"{ARCHIVE.format(cik=cik, acc=accession.replace('-', ''))}/{instance_filename(primary_document)}"
