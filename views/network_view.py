"""Interactive 'who pays whom' network (part of the Demand tab)."""
from __future__ import annotations

import json
import math
from pathlib import Path

import pandas as pd
import streamlit as st

from ai_capital_cycle.network import (DEAL_TYPES, GROUP_LABELS, deals_on_loop, filter_deals, find_loops,
                                      load_deals, node_table)

ROOT = Path(__file__).resolve().parents[1]
DEALS_PATH = ROOT / "data" / "ai_deals.csv"

GROUP_COLORS = {"cloud": "#2a78d6", "chips": "#eb6834", "ai_lab": "#1baf7a", "ai_user": "#e87ba4",
                "investor": "#6250d6"}
TYPE_STYLE = {  # colour + dash pattern, so type never relies on colour alone
    "investment": ("#eda100", [6, 4], "Investment"),
    "cloud": ("#008300", False, "Cloud contract"),
    "chips": ("#e34948", [2, 4], "Chip purchase"),
    "manufacturing": ("#8a8984", [1, 3], "Chip manufacturing"),
}
TYPE_LABELS = {k: v[2] for k, v in TYPE_STYLE.items()}
STATUS_LABELS = {"completed": "completed", "announced": "announced", "filed": "in an SEC filing",
                 "reported": "press reports only", "background": "ongoing supply relationship"}


def _amount(row) -> str:
    if pd.isna(row.amount_usd_bn):
        return "amount not disclosed"
    prefix = {"up_to": "up to ", "approximate": "about ", "reported": "reportedly "}.get(row.amount_kind, "")
    return f"{prefix}${row.amount_usd_bn:,.1f}B".replace(".0B", "B")


def _graph_payload(deals: pd.DataFrame, nodes: pd.DataFrame, highlight: set[tuple[str, str]], dark: bool) -> dict:
    ink = "#f0efec" if dark else "#0b0b0b"
    muted = "#c3c2b7" if dark else "#52514e"
    vis_nodes = []
    for n in nodes.itertuples():
        color = GROUP_COLORS.get(n.group, "#8a8984")
        vis_nodes.append({
            "id": n.company, "label": n.company, "value": int(n.connections),
            "color": {"background": color, "border": color,
                      "highlight": {"background": color, "border": ink}},
            "font": {"color": ink, "size": 14, "strokeWidth": 3, "strokeColor": "#1a1a19" if dark else "#fcfcfb"},
            "info": f"{n.company} · {GROUP_LABELS.get(n.group, n.group)} · {n.connections} connections, "
                    f"{n.deals} deals",
        })
    vis_edges = []
    for i, d in enumerate(deals.itertuples()):
        color, dashes, label = TYPE_STYLE[d.type]
        on_loop = (d.payer, d.receiver) in highlight
        faded = bool(highlight) and not on_loop
        width = 1.0 if pd.isna(d.amount_usd_bn) else 1.0 + 1.6 * math.log10(1 + d.amount_usd_bn)
        vis_edges.append({
            "id": i, "from": d.payer, "to": d.receiver, "arrows": "to",
            "width": width * (1.6 if on_loop else 1.0), "dashes": dashes,
            "color": {"color": color, "opacity": 0.15 if faded else 0.85, "highlight": color},
            "smooth": {"type": "curvedCW", "roundness": 0.15},
            "info": {"title": f"{d.payer} → {d.receiver}", "type": label, "amount": _amount(d),
                     "when": "" if pd.isna(d.announced) else d.announced.strftime("%b %Y"),
                     "status": STATUS_LABELS[d.status], "what": d.what, "url": d.source_url},
        })
    return {"nodes": vis_nodes, "edges": vis_edges, "ink": ink, "muted": muted}


HTML = """
<div id="wrap" style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;color:__INK__">
  <div id="net" style="height:470px;border:1px solid rgba(128,128,128,.25);border-radius:12px;touch-action:none"></div>
  <div style="display:flex;gap:8px;margin:8px 0">
    <button id="fit" style="padding:6px 12px;border-radius:8px;border:1px solid rgba(128,128,128,.4);
      background:transparent;color:__INK__;font-size:14px">Show whole map</button>
    <span style="color:__MUTED__;font-size:13px;align-self:center">Pinch to zoom · drag to move · tap a company or arrow</span>
  </div>
  <div id="info" style="font-size:14px;line-height:1.45;min-height:48px;color:__INK__"></div>
</div>
<script src="https://unpkg.com/vis-network@9.1.9/standalone/umd/vis-network.min.js"></script>
<script>
const data = __DATA__;
const nodes = new vis.DataSet(data.nodes), edges = new vis.DataSet(data.edges);
const net = new vis.Network(document.getElementById("net"), {nodes, edges}, {
  nodes: {shape: "dot", scaling: {min: 10, max: 46, label: {enabled: true, min: 12, max: 22}}, borderWidth: 2},
  edges: {selectionWidth: 2, hoverWidth: 0},
  physics: {solver: "forceAtlas2Based", forceAtlas2Based: {gravitationalConstant: -60, springLength: 120},
            stabilization: {iterations: 400}},
  interaction: {hover: true, tooltipDelay: 150, zoomView: true, dragView: true, navigationButtons: false},
});
net.once("stabilizationIterationsDone", () => { net.setOptions({physics: false}); net.fit(); });
document.getElementById("fit").onclick = () => net.fit({animation: true});
const info = document.getElementById("info");
const esc = s => String(s).replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
function dealLine(e) {
  const i = e.info;
  return `<div style="margin:6px 0"><b>${esc(i.title)}</b> · ${esc(i.type)} · ${esc(i.amount)}` +
    (i.when ? ` · ${esc(i.when)}` : "") + ` <span style="color:__MUTED__">(${esc(i.status)})</span><br>` +
    `${esc(i.what)} <a href="${esc(i.url)}" target="_blank" rel="noopener">source ↗</a></div>`;
}
net.on("click", p => {
  if (p.nodes.length) {
    const n = nodes.get(p.nodes[0]);
    const list = edges.get().filter(e => e.from === n.id || e.to === n.id);
    info.innerHTML = `<div style="font-weight:600;margin-bottom:4px">${esc(n.info)}</div>` + list.map(dealLine).join("");
  } else if (p.edges.length) {
    info.innerHTML = dealLine(edges.get(p.edges[0]));
  } else {
    info.innerHTML = "";
  }
});
</script>
"""


def render() -> None:
    st.subheader("Who pays whom")
    st.markdown("Each arrow is money moving from one company to another: an investment, a cloud contract or a "
                "chip purchase. Bigger circles have more connections. Follow the arrows to see how money can "
                "come back to where it started.")
    deals_all = load_deals(DEALS_PATH)

    with st.expander("Map settings"):
        types = st.multiselect("Show these kinds of deal", list(DEAL_TYPES), default=list(DEAL_TYPES),
                               format_func=TYPE_LABELS.get, key="net_types")
        background = st.toggle("Include ongoing supply relationships (no single deal)", value=True, key="net_bg",
                               help="E.g. Microsoft buying Nvidia chips: certain, but not one announced contract.")
        reported = st.toggle("Include deals known only from press reports", value=True, key="net_rep")
    deals = filter_deals(deals_all, types or DEAL_TYPES, background, reported)
    if deals.empty:
        st.info("No deals match these settings.")
        return
    nodes = node_table(deals)
    loops = find_loops(deals, max_length=3)
    loop_names = ["None"] + [" → ".join(l + [l[0]]) for l in loops]
    pick = st.selectbox("Highlight a money loop", loop_names, key="net_loop",
                        help="Loops where money paid out by a company comes back to it through other companies.")
    highlight: set[tuple[str, str]] = set()
    if pick != "None":
        loop = loops[loop_names.index(pick) - 1]
        highlight = set(zip(loop, loop[1:] + loop[:1]))

    dark = getattr(getattr(st.context, "theme", None), "type", "light") == "dark"
    payload = _graph_payload(deals, nodes, highlight, dark)
    html = (HTML.replace("__DATA__", json.dumps(payload)).replace("__INK__", payload["ink"])
            .replace("__MUTED__", payload["muted"]))
    if hasattr(st, "iframe"):          # Streamlit's replacement for components.html
        st.iframe(html, height=640)
    else:
        import streamlit.components.v1 as components
        components.html(html, height=640, scrolling=True)

    legend = " · ".join(f"**{GROUP_LABELS[g]}** <span style='color:{c}'>●</span>" for g, c in GROUP_COLORS.items())
    lines = " · ".join(f"{label} <span style='color:{c}'>{'━' if not dash else '╍'}</span>"
                       for c, dash, label in TYPE_STYLE.values())
    st.markdown(f"<small>{legend}<br>{lines} · thicker arrow = bigger amount</small>", unsafe_allow_html=True)

    if pick != "None":
        st.markdown(f"**Loop:** {pick}")
        for d in deals_on_loop(deals, loop).itertuples():
            st.markdown(f"- {d.payer} → {d.receiver}: {TYPE_LABELS[d.type].lower()}, {_amount(d)}. {d.what} "
                        f"([source]({d.source_url}))")

    c1, c2 = st.columns(2)
    c1.metric("Companies on the map", len(nodes))
    c2.metric("Money loops (2–3 companies)", len(loops),
              help="Chains where money flows out and comes back, e.g. Nvidia invests in OpenAI, which buys "
                   "Nvidia chips. Common in this industry; they can inflate how much demand looks independent.")
    st.caption("Why loops matter: if a supplier funds its own customers, part of its sales is paid for with its "
               "own money. That isn't necessarily wrong, but it means some demand depends on the investment cycle "
               "continuing rather than on end customers.")

    with st.expander("All deals and sources"):
        company = st.selectbox("Company", ["All"] + nodes["company"].tolist(), key="net_company")
        table = deals if company == "All" else deals[(deals.payer == company) | (deals.receiver == company)]
        st.dataframe(pd.DataFrame({
            "From": table["payer"], "To": table["receiver"], "Kind": table["type"].map(TYPE_LABELS),
            "Amount": [_amount(r) for r in table.itertuples()],
            "When": table["announced"].dt.strftime("%b %Y").fillna(""),
            "Status": table["status"].map(STATUS_LABELS), "What": table["what"], "Source": table["source_url"],
        }), hide_index=True, width="stretch",
            column_config={"Source": st.column_config.LinkColumn(display_text="source ↗")})
        st.caption(f"Hand-collected from company announcements, SEC filings and press reports; "
                   f"{len(deals_all)} deals, latest {deals_all['announced'].max():%d %b %Y}. "
                   "Unlike the rest of the app it is not updated automatically. Amounts are what was announced "
                   "(often 'up to' or multi-year commitments), not money already paid.")
