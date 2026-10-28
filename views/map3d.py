"""3D 'who pays whom' map: HTML shared by the Streamlit app and the standalone preview.

The page loads ``static/map3d.min.js`` (our own bundle of 3d-force-graph, three-spritetext
and three.js; see scripts/build_map3d.sh), which defines the global ``Map3D``.
"""
from __future__ import annotations

import json
import math

import pandas as pd

from ai_capital_cycle.network import GROUP_LABELS, SHORT_NAMES, find_loops, node_table

# The app loads the bundle from jsDelivr's GitHub mirror, pinned to the commit that
# added it, so the file can never change underneath the app.
BUNDLE_COMMIT = "e4ff4f4e77f0e8e266d8519572f2609eb58189a4"
BUNDLE_URL = ("https://cdn.jsdelivr.net/gh/danielong3011-pixel/ai-capital-cycle-monitor@"
              f"{BUNDLE_COMMIT}/static/map3d.min.js")

GROUP_COLORS = {"cloud": "#2a78d6", "chips": "#eb6834", "ai_lab": "#1baf7a", "ai_user": "#d55181",
                "investor": "#6250d6"}
TYPE_STYLE = {"investment": ("#eda100", "Investment"), "cloud": ("#008300", "Cloud contract"),
              "chips": ("#e34948", "Chip purchase"), "manufacturing": ("#8a8984", "Chip manufacturing")}
STATUS_LABELS = {"completed": "completed", "announced": "announced", "filed": "in an SEC filing",
                 "reported": "press reports only", "background": "ongoing supply relationship"}


def amount_text(row) -> str:
    if pd.isna(row.amount_usd_bn):
        return "amount not disclosed"
    prefix = {"up_to": "up to ", "approximate": "about ", "reported": "reportedly "}.get(row.amount_kind, "")
    return f"{prefix}${row.amount_usd_bn:,.1f}B".replace(".0B", "B")


def graph_data(deals: pd.DataFrame) -> dict:
    nodes = node_table(deals)
    out_nodes = [{
        "id": n.company, "short": SHORT_NAMES.get(n.company, n.company), "color": GROUP_COLORS.get(n.group, "#8a8984"),
        "val": int(n.connections) ** 2,
        "info": f"{n.company} · {GROUP_LABELS.get(n.group, n.group)} · {n.connections} connections, {n.deals} deals",
    } for n in nodes.itertuples()]
    pairs = list(zip(deals["payer"], deals["receiver"]))
    seen: dict[frozenset, int] = {}
    links = []
    for i, d in enumerate(deals.itertuples()):
        key = frozenset((d.payer, d.receiver))
        k = seen.get(key, 0)
        seen[key] = k + 1
        reciprocal = (d.receiver, d.payer) in pairs
        color, label = TYPE_STYLE[d.type]
        links.append({
            "id": i, "source": d.payer, "target": d.receiver, "color": color,
            "width": 0.35 if pd.isna(d.amount_usd_bn) else 0.35 + 0.55 * math.log10(1 + d.amount_usd_bn),
            "curv": (0.25 + 0.15 * k) if (reciprocal or k) else 0.0,
            "rot": (k * math.pi / 2),
            "info": {"title": f"{d.payer} → {d.receiver}", "type": label, "amount": amount_text(d),
                     "when": "" if pd.isna(d.announced) else d.announced.strftime("%b %Y"),
                     "status": STATUS_LABELS[d.status], "what": d.what, "url": d.source_url},
        })
    loops = [loop + [loop[0]] for loop in find_loops(deals, max_length=3)]
    return {"nodes": out_nodes, "links": links, "loops": loops}


def legend_html() -> str:
    groups = "".join(f'<span class="key"><i class="dot" style="background:{c}"></i>{GROUP_LABELS[g]}</span>'
                     for g, c in GROUP_COLORS.items())
    types = "".join(f'<span class="key"><i class="bar" style="background:{c}"></i>{label}</span>'
                    for c, label in TYPE_STYLE.values())
    return (f'<div class="legend">{groups}</div><div class="legend">{types}'
            '<span class="key">moving dots = direction of money · thicker = bigger amount</span></div>')


STYLE = """
:root {
  --bg: #f7f7f5; --surface: #ffffff; --fg: #17171a; --muted: #5d5d66; --rule: #dcdcd8; --accent: #2a78d6;
  --font-ui: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  --font-data: ui-monospace, SFMono-Regular, Menlo, monospace;
}
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {
  --bg: #141416; --surface: #1c1c1f; --fg: #ececee; --muted: #a3a3ad; --rule: #34343a; --accent: #3987e5;
  color-scheme: dark } }
:root[data-theme="dark"] { --bg: #141416; --surface: #1c1c1f; --fg: #ececee; --muted: #a3a3ad; --rule: #34343a;
  --accent: #3987e5; color-scheme: dark }
.m3 { font-family: var(--font-ui); color: var(--fg); display: grid; gap: 10px; font-size: 14px; line-height: 1.45 }
#graph { height: __HEIGHT__px; background: var(--surface); border: 1px solid var(--rule); border-radius: 12px;
  overflow: hidden; touch-action: none; position: relative }
.bar-row { display: flex; flex-wrap: wrap; gap: 8px; align-items: center }
.m3 button, .m3 select { font: inherit; font-size: 14px; color: var(--fg); background: var(--surface);
  border: 1px solid var(--rule); border-radius: 8px; padding: 6px 10px; max-width: 100% }
.m3 button:focus-visible, .m3 select:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px }
.hint { font-size: 13px; color: var(--muted) }
.legend { display: flex; flex-wrap: wrap; gap: 6px 14px; font-size: 13px; color: var(--muted) }
.key { display: inline-flex; align-items: center; gap: 6px }
.dot { width: 10px; height: 10px; border-radius: 50%; display: inline-block }
.bar { width: 18px; height: 4px; border-radius: 2px; display: inline-block }
#info { background: var(--surface); border: 1px solid var(--rule); border-radius: 12px; padding: 10px 14px; min-height: 2.5em }
#info:empty::before { content: "Tap a company or an arrow to see the deals behind it."; color: var(--muted) }
.deal { padding: 8px 0; border-top: 1px solid var(--rule) } .deal:first-of-type { border-top: 0 }
.amt { font-family: var(--font-data); font-variant-numeric: tabular-nums }
.st { color: var(--muted); font-size: 13px }
.m3 a { color: var(--accent) }
#fallback { padding: 16px; color: var(--muted) }
"""

BODY = """
<div class="m3">
  <div id="graph" role="img" aria-label="3D network of money flows between AI companies"></div>
  <div class="bar-row">
    <button id="reset" type="button">Show whole map</button>
    <button id="spin" type="button" aria-pressed="true">Pause spin</button>
    <label for="loop" class="hint">Money loop</label>
    <select id="loop"><option value="">None</option></select>
  </div>
  <div class="hint">Drag with one finger to turn it · pinch to zoom · tap a company or arrow</div>
  __LEGEND__
  <div id="info" aria-live="polite"></div>
</div>
"""

SCRIPT = """
(function () {
  const DATA = __DATA__;
  const host = document.getElementById("graph");
  if (!window.Map3D) { host.innerHTML = '<div id="fallback">The 3D map could not load. Check your connection and reload.</div>'; return; }
  const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
  const esc = s => String(s).replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
  const info = document.getElementById("info");
  const select = document.getElementById("loop");
  DATA.loops.forEach((l, i) => { const o = document.createElement("option"); o.value = i; o.textContent = l.join(" → "); select.appendChild(o); });

  let active = null;          // set of "payer>receiver" on the highlighted loop
  const on = l => !active || active.has(l.source.id + ">" + l.target.id) || active.has(l.source + ">" + l.target);
  const alpha = (hex, a) => { const v = parseInt(hex.slice(1), 16); return `rgba(${v >> 16},${(v >> 8) & 255},${v & 255},${a})`; };

  const Graph = new Map3D.ForceGraph3D(host, { controlType: "orbit" })
    .width(host.clientWidth).height(host.clientHeight)
    .backgroundColor(css("--surface")).showNavInfo(false)
    .graphData({ nodes: DATA.nodes, links: DATA.links })
    .nodeRelSize(3).nodeVal("val").nodeColor("color").nodeOpacity(0.95).nodeResolution(24)
    .nodeLabel(n => esc(n.info))
    .nodeThreeObjectExtend(true)
    .nodeThreeObject(n => {
      const r = Math.cbrt(n.val) * 3;
      const t = new Map3D.SpriteText(n.short, Math.max(2.6, r * 0.5), "#ffffff");
      t.fontWeight = "700"; t.strokeWidth = 1.2; t.strokeColor = "rgba(0,0,0,0.55)";
      t.material.depthTest = false; t.material.depthWrite = false; t.renderOrder = 10;
      return t;
    })
    .linkColor(l => alpha(l.color, on(l) ? 0.85 : 0.08))
    .linkWidth(l => on(l) ? l.width * (active ? 1.8 : 1) : l.width * 0.6)
    .linkCurvature("curv").linkCurveRotation("rot")
    .linkDirectionalArrowLength(l => on(l) ? 3.5 : 0).linkDirectionalArrowRelPos(1)
    .linkDirectionalArrowColor(l => alpha(l.color, 0.95))
    .linkDirectionalParticles(l => on(l) ? 2 : 0).linkDirectionalParticleWidth(l => 0.9 + l.width)
    .linkDirectionalParticleSpeed(0.006).linkDirectionalParticleColor(l => l.color)
    .linkLabel(l => esc(l.info.title + " · " + l.info.type + " · " + l.info.amount))
    .warmupTicks(80).cooldownTicks(120);

  Graph.d3Force("charge").strength(-140);
  const controls = Graph.controls();
  controls.autoRotate = true; controls.autoRotateSpeed = 0.9;
  const spin = document.getElementById("spin");
  const setSpin = v => { controls.autoRotate = v; spin.textContent = v ? "Pause spin" : "Spin"; spin.setAttribute("aria-pressed", String(v)); };
  spin.onclick = () => setSpin(!controls.autoRotate);
  controls.addEventListener("start", () => setSpin(false));
  let fitted = false;
  Graph.onEngineStop(() => { if (!fitted) { fitted = true; Graph.zoomToFit(600, 30); } });
  document.getElementById("reset").onclick = () => Graph.zoomToFit(800, 30);

  const line = l => { const i = l.info; return `<div class="deal"><b>${esc(i.title)}</b> · ${esc(i.type)} · <span class="amt">${esc(i.amount)}</span>` +
    (i.when ? ` · ${esc(i.when)}` : "") + ` <span class="st">(${esc(i.status)})</span><br>${esc(i.what)} ` +
    `<a href="${esc(i.url)}" target="_blank" rel="noopener">source ↗</a></div>`; };
  const nodeId = x => (typeof x === "object" ? x.id : x);
  Graph.onNodeClick(n => {
    setSpin(false);
    const list = DATA.links.filter(l => nodeId(l.source) === n.id || nodeId(l.target) === n.id);
    info.innerHTML = `<div><b>${esc(n.info)}</b></div>` + list.map(line).join("");
    const d = 1 + 90 / Math.hypot(n.x || 1, n.y || 1, n.z || 1);
    Graph.cameraPosition({ x: n.x * d, y: n.y * d, z: n.z * d }, n, 900);
  });
  Graph.onLinkClick(l => { setSpin(false); info.innerHTML = line(l); });
  Graph.onBackgroundClick(() => { info.innerHTML = ""; });

  const refresh = () => Graph.linkColor(Graph.linkColor()).linkWidth(Graph.linkWidth())
    .linkDirectionalParticles(Graph.linkDirectionalParticles()).linkDirectionalArrowLength(Graph.linkDirectionalArrowLength());
  select.onchange = () => {
    const v = select.value;
    if (v === "") { active = null; info.innerHTML = ""; refresh(); return; }
    const loop = DATA.loops[+v]; active = new Set();
    for (let i = 0; i < loop.length - 1; i++) active.add(loop[i] + ">" + loop[i + 1]);
    refresh(); setSpin(false);
    info.innerHTML = `<div><b>Loop: ${esc(loop.join(" → "))}</b></div>` +
      DATA.links.filter(l => active.has(nodeId(l.source) + ">" + nodeId(l.target))).map(line).join("");
  };

  const theme = () => Graph.backgroundColor(css("--surface"));
  try { matchMedia("(prefers-color-scheme: dark)").addEventListener("change", theme); } catch (e) {}
  new MutationObserver(theme).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
  addEventListener("resize", () => Graph.width(host.clientWidth).height(host.clientHeight));
})();
"""


def build(deals: pd.DataFrame, *, script_src: str = BUNDLE_URL, height: int = 520, theme: str | None = None) -> str:
    """HTML fragment for the 3D map (style, markup, bundle and app script)."""
    data = json.dumps(graph_data(deals)).replace("</", "<\\/")
    theme_attr = (f"<script>document.documentElement.setAttribute('data-theme','{theme}')</script>"
                  if theme in ("light", "dark") else "")
    return (f"<style>{STYLE.replace('__HEIGHT__', str(height))}</style>{theme_attr}"
            f"{BODY.replace('__LEGEND__', legend_html())}"
            f'<script src="{script_src}"></script><script>{SCRIPT.replace("__DATA__", data)}</script>')
