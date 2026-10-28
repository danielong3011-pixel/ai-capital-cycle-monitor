#!/usr/bin/env bash
# Rebuilds static/map3d.min.js: one browser bundle exposing the global Map3D = {ForceGraph3D, SpriteText}.
# Bundling guarantees the graph library and the text labels share a single copy of three.js.
set -euo pipefail
work=$(mktemp -d)
cd "$work"
npm init -y >/dev/null
npm install --no-audit --no-fund 3d-force-graph@1.80.0 three-spritetext@1.10.0 three@0.186.1 esbuild@0.25.10
printf 'import ForceGraph3D from "3d-force-graph";\nimport SpriteText from "three-spritetext";\nexport { ForceGraph3D, SpriteText };\n' > entry.js
npx esbuild entry.js --bundle --minify --format=iife --global-name=Map3D --target=es2020 --legal-comments=none --outfile=out.js
cd - >/dev/null
{ printf '/*! map3d bundle for AI Capital Cycle Monitor: 3d-force-graph 1.80.0 (MIT), three-spritetext 1.10.0 (MIT), three.js 0.186.1 (MIT), d3-force-3d and dependencies (ISC/MIT). Rebuild with scripts/build_map3d.sh. */\n'; cat "$work/out.js"; } > static/map3d.min.js
echo "Wrote static/map3d.min.js"
