# AI Capital Cycle Monitor

An independent, open-source Python research prototype exploring the financial sustainability of AI infrastructure investment. **This is not a bubble-timing or market-crash prediction tool.**

## What it does

**Capital cycle (Module A)** uses real SEC filings to track the companies building AI compute:
Microsoft, Amazon, Alphabet, Meta, Oracle and CoreWeave, with Nvidia as a supplier cross-check.
- Trailing-twelve-month CapEx, operating cash flow, free cash flow, reinvestment rate, capital
  intensity, CapEx/depreciation, funding gap, net debt issuance and debt-funded share of CapEx.
- Fiscal quarters (June, May and January year-ends) aligned to calendar quarters; discrete quarters
  derived from year-to-date cash-flow statements.
- Coverage-aware aggregates: a quarter only counts once every selected company has filed.
- No double counting along the value chain: supplier revenue is never added to spender CapEx.
- Point-in-time view: rebuild any reading from only the filings available on a past date.
- Full provenance: every quarterly figure links to the SEC filing it came from.

**Project model** (version 0.1) is an illustrative single-project DCF with sensitivity and
Monte Carlo scenarios, plus a CSV aggregator for your own documented observations.

## Data

`data/sec_facts.csv` is a snapshot of SEC EDGAR XBRL company facts, refreshed every Monday by
`.github/workflows/refresh-sec-data.yml`. SEC requires a contact in the User-Agent: the workflow
reads it from the repository secret `SEC_USER_AGENT`. To refresh locally:

```bash
SEC_USER_AGENT="Your Name you@example.com" python scripts/refresh_sec_data.py
```

The company list and the XBRL tags used for each line item are in
`src/ai_capital_cycle/universe.py`. The full method is in the app's **Method & data** tab.

## Important limitations
Reported CapEx is total company investment, not AI-only (Amazon's includes retail logistics).
Finance-lease and off-balance-sheet data-centre capacity is not in cash CapEx. Private labs and
non-US companies are not yet covered. Figures are nominal USD. The project model and
`data/industry_template.csv` are illustrative. Nothing here is investment advice.

## Run locally or in GitHub Codespaces

```bash
python -m pip install -e '.[dev]'
streamlit run app.py --server.address 0.0.0.0
```

In Codespaces, open the forwarded Streamlit port **8501** to view the app on a phone. On GitHub: create a new repository, upload the extracted project files, then choose **Code → Codespaces → Create codespace on main**. The first Codespaces launch may take a few minutes.

Run tests:

```bash
python -m pytest -q
```

## CSV schema
`year, company, segment, capex_usd_bn, operating_cash_flow_usd_bn, source, ai_capex_share, ai_capex_share_basis`

`ai_capex_share` must be in [0, 1]. It is an estimate unless a credible disclosure directly supports it. Record full source URLs and reporting periods in a future data-provenance version. Never treat an illustrative share as a reported fact.

## Planned next steps
1. End-customer AI revenue ledger that separates final demand from intermediate transactions.
2. Incremental ROIC, asset cohorts and replacement-cycle modelling.
3. Wider coverage (semiconductors, neoclouds, 20-F filers) and finance-lease-adjusted CapEx.
4. Historical validation with point-in-time vintages and stress tests.

## License
See `LICENSE`.

## Publish a Safari-accessible website (Streamlit Community Cloud)

1. Create a GitHub repository and upload the contents of this folder (keep `app.py`, `requirements.txt`, `pyproject.toml`, and `src/` at repository root).
   **Keep the folder structure.** If you upload through GitHub's web page, drag the folders themselves (`src`, `data`, `tests`, `.streamlit`), not the individual `.py` files inside them; uploading loose files places them all at the root and causes `ModuleNotFoundError: No module named 'ai_capital_cycle'`.
2. Visit https://share.streamlit.io/ and sign in with GitHub.
3. Choose **Create app** / **Deploy an app**, select your repository and branch, and set the main file path to `app.py`. Under **Advanced settings**, choose Python 3.10 or newer.
4. Deploy. Once it finishes, open the assigned `*.streamlit.app` link in Safari. Bookmark or share the link.

This deployment runs the Python app on Streamlit's servers; Safari only displays the website. The app contains fictional demo data, not live AI industry observations. Deployment requires the repository owner to authorize access and cannot be completed by downloading this ZIP alone.
