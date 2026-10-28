# AI Capital Cycle Monitor

An independent, open-source Python research prototype exploring the financial sustainability of AI infrastructure investment. **This is not a bubble-timing or market-crash prediction tool.**

## Current capabilities
- Transparent project DCF and numerical break-even growth calculation.
- Growth/discount-rate sensitivity table.
- Industry observation CSV import, strict validation and year-level aggregation.
- AI-attributed CapEx shown separately from reported total CapEx, with an explicit assumption field.
- Reproducible Monte Carlo NPV scenarios with adjustable uncertainty.
- Streamlit interactive dashboard and automated pytest tests.

## Important limitations
**The bundled `data/industry_template.csv` is fictional.** No live financial data is bundled and no output should be presented as a current industry estimate. Reported corporate CapEx is not identical to AI CapEx. Summing company-level capital spending across a carefully chosen universe is not the same as measuring the entire industry. The model is an illustrative investment project, not an empirically calibrated aggregate industry valuation. Simulation frequencies are conditional on selected assumptions, not actual event probabilities. Additional research must address capex timing, hardware replacement, taxes, terminal value, supply-chain double counting, industry coverage and point-in-time source records.

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
1. SEC EDGAR ingestion with filing URLs, accession IDs, units, and as-of timestamps.
2. Coverage-aware industry aggregates and an end-customer revenue ledger that avoids double counting.
3. Incremental ROIC, infrastructure asset cohorts and replacement capital modelling.
4. Historical validation with vintage data and stress-test transmission to equities.

## License
See `LICENSE`.

## Publish a Safari-accessible website (Streamlit Community Cloud)

1. Create a GitHub repository and upload the contents of this folder (keep `app.py`, `requirements.txt`, `pyproject.toml`, and `src/` at repository root).
   **Keep the folder structure.** If you upload through GitHub's web page, drag the folders themselves (`src`, `data`, `tests`, `.streamlit`), not the individual `.py` files inside them; uploading loose files places them all at the root and causes `ModuleNotFoundError: No module named 'ai_capital_cycle'`.
2. Visit https://share.streamlit.io/ and sign in with GitHub.
3. Choose **Create app** / **Deploy an app**, select your repository and branch, and set the main file path to `app.py`. Under **Advanced settings**, choose Python 3.10 or newer.
4. Deploy. Once it finishes, open the assigned `*.streamlit.app` link in Safari. Bookmark or share the link.

This deployment runs the Python app on Streamlit's servers; Safari only displays the website. The app contains fictional demo data, not live AI industry observations. Deployment requires the repository owner to authorize access and cannot be completed by downloading this ZIP alone.
