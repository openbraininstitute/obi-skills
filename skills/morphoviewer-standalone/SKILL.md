---
name: morphoviewer-standalone
description: Guide for generating standalone interactive HTML pages displaying neuron morphologies or circuits using @openbraininstitute/morphoviewer. Use when the user wants to visualize morphologies or circuits in a browser from data fetched via the OBI REST APIs. The generated page is self-contained and requires no server once opened.
license: Apache-2.0
---

# Standalone Morphology & Circuit Viewer Pages

> **Generic skills this one builds on — follow them, don't re-derive:**
> - [[obi-sandbox-auth]] — how to obtain, exchange, and refresh OBI credentials for the EntityCore/obi-one fetches below. Never construct auth calls ad hoc.
> - [[chat-obi-sandbox-bridge]] — (Claude Chat / Claude Desktop) if the morphology/circuit data is assembled on the OBI sandbox, bridge the generated HTML back to the user from there rather than writing it locally.
> - [[obi-logbook]] — **mandatory** when the visualization is part of a scientific session: record what was visualized and what it shows. See the Logbook section below.
> - [[obi-links]] — the visualized entities and the generated HTML page are handed to the user as hyperlinks, never as bare UUIDs or paths. See the Linking section below.

## Overview

Generate self-contained HTML files that display interactive 3D neuron morphologies or circuits using `@openbraininstitute/morphoviewer` (public npm package). The page loads the library from esm.sh CDN and inlines all data — no backend needed once opened.

Two use cases:
1. **Single morphology** — display one SWC file using `MorphologyCanvas` (imperative API, no React needed)
2. **Circuit** — display positioned neurons using `MorphoViewerSmallCircuit` (React component) or `MorphoViewerSomasOnly` (soma spheres for large circuits)

## Data Sources

### Morphology (SWC file)

Fetch from EntityCore:
```
GET /api/entitycore/cell-morphology/{id}/assets/{asset_id}/download
```

The asset with `content_type: "application/swc"` or label `"morphology"` contains the SWC text.

### Circuit nodes + morphologies

From obi-one:
```
GET /api/obi-one/circuit/viz/{circuit_id}/nodes
→ [{morphology_file, morphology_name, position, orientation}]

GET /api/obi-one/circuit/viz/{circuit_id}/morphologies/{file}?name={name}
→ [{id, parent_id, type, points: [[x,y,z],...], radii: [float,...]}]
```

Both require headers: `Authorization: Bearer <token>`, `virtual-lab-id`, `project-id`. Take the last two from `$OBI_VLAB_ID` / `$OBI_PROJECT_ID` in the sandbox rather than remembered values — see [[virtual-lab-manager-api]].

## Template 1: Single Morphology (SWC)

This uses `MorphologyCanvas` — a plain JavaScript class that renders SWC content to a canvas element. No React required.

```html
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Morphology Viewer</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body { width: 100vw; height: 100vh; overflow: hidden; background: #1a1a1a; }
    canvas { width: 100%; height: 100%; display: block; }
    .info { position: absolute; top: 12px; left: 12px; color: #aaa; font: 13px/1.4 system-ui; }
  </style>
</head>
<body>
  <canvas id="viewer"></canvas>
  <div class="info">
    <strong>__MORPHOLOGY_NAME__</strong><br>
    Scroll to zoom · Drag to rotate · Ctrl+drag to pan
  </div>
  <script type="module">
    import { MorphologyCanvas } from 'https://esm.sh/@openbraininstitute/morphoviewer@0.32.1';

    const canvas = document.getElementById('viewer');
    const viewer = new MorphologyCanvas();
    viewer.canvas = canvas;
    viewer.colors.background = '#1a1a1a';

    // SWC content inlined as a template literal
    viewer.swc = `__SWC_CONTENT__`;
  </script>
</body>
</html>
```

### How to generate

1. Fetch the SWC file content from EntityCore (download the morphology asset)
2. Replace `__SWC_CONTENT__` with the SWC text (escape backticks if any)
3. Replace `__MORPHOLOGY_NAME__` with the entity name
4. Save as `.html` and open in browser

### SWC Format Reference

Standard SWC is a space-separated text file:
```
# Comments start with #
# id type x y z radius parent_id
1 1 0.0 0.0 0.0 5.0 -1
2 3 10.0 0.0 0.0 1.5 1
...
```

Types: 1=soma, 2=axon, 3=basal dendrite, 4=apical dendrite.

## Template 2: Small Circuit (with morphologies)

This uses `MorphoViewerSmallCircuit` — a React component. The page needs React + ReactDOM.

```html
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Circuit Viewer</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body { width: 100vw; height: 100vh; overflow: hidden; }
    #root { width: 100%; height: 100%; }
  </style>
</head>
<body>
  <div id="root"></div>
  <script type="importmap">
  {
    "imports": {
      "react": "https://esm.sh/react@19.1.0",
      "react-dom/client": "https://esm.sh/react-dom@19.1.0/client",
      "@openbraininstitute/morphoviewer": "https://esm.sh/@openbraininstitute/morphoviewer@0.32.1?external=react"
    }
  }
  </script>
  <script type="module">
    import React from 'react';
    import { createRoot } from 'react-dom/client';
    import { MorphoViewerSmallCircuit, MorphoViewerSignals } from '@openbraininstitute/morphoviewer';

    // === INLINED DATA ===

    // Nodes: array of {position, orientation} per neuron
    const nodes = __NODES_JSON__;

    // Morphologies: map of cell_id → section tree
    const morphologies = __MORPHOLOGIES_JSON__;

    // === BUILD CELLS ===

    const cells = nodes.map((node, i) => ({
      id: `cell-${i}`,
      center: node.position,
      orientation: node.orientation,
      somaRadius: 8,
      color: '#4a90d9',
    }));

    // === TREE BUILDER ===
    // Convert section array to morphoviewer tree format

    function buildTree(sections, cellId) {
      const roots = [];
      const terminalNodes = new Map();
      const somaNodes = [];

      for (const sec of sections) {
        let prevNode = null;

        if (sec.parent_id === 'soma' && somaNodes.length > 0) {
          prevNode = somaNodes[0];
        } else if (sec.parent_id !== null && sec.parent_id !== 'soma') {
          prevNode = terminalNodes.get(sec.parent_id) || null;
        }

        const isSoma = sec.id === 'soma';
        const startIdx = (sec.parent_id === null || sec.parent_id === 'soma') ? 0 : 1;
        let lastNode = prevNode;

        for (let i = startIdx; i < sec.points.length; i++) {
          const [x, y, z] = sec.points[i];
          const node = {
            x, y, z,
            radius: sec.radii[i],
            type: sec.type,
            sectionId: sec.id,
            segmentId: String(i),
            distanceFromSoma: 0,
          };

          if (!lastNode && !isSoma) roots.push(node);
          else if (isSoma && i === 0) roots.push(node);
          else if (lastNode) {
            lastNode.children = lastNode.children || [];
            lastNode.children.push(node);
          }

          lastNode = node;
          if (isSoma) somaNodes.push(node);
        }

        if (lastNode && !isSoma) terminalNodes.set(sec.id, lastNode);
      }

      return { type: 'tree', data: { cellId, roots } };
    }

    // === LOAD CELL ===

    async function loadCell(cellId) {
      const sections = morphologies[cellId];
      if (!sections) return null;
      return buildTree(sections, cellId);
    }

    // === RENDER ===

    const signals = new MorphoViewerSignals();

    function App() {
      return React.createElement(MorphoViewerSmallCircuit, {
        className: 'w-full h-full',
        gizmo: true,
        scalebar: { length: 100, label: '100 μm', color: '#ffffff' },
        backgroundColor: '#1a1a1a',
        signals,
        circuit: cells,
        loadCell,
        controls: [],
      });
    }

    createRoot(document.getElementById('root')).render(React.createElement(App));
  </script>
</body>
</html>
```

### How to generate

1. Fetch nodes from `GET /api/obi-one/circuit/viz/{circuit_id}/nodes`
2. For each node, fetch morphology from `GET /api/obi-one/circuit/viz/{circuit_id}/morphologies/{file}?name={name}`
3. Build a morphologies map: `{ "cell-0": sections_array, "cell-1": sections_array, ... }`
4. Replace `__NODES_JSON__` with the nodes array
5. Replace `__MORPHOLOGIES_JSON__` with the morphologies map
6. Save as `.html` and open in browser

### Section Data Format (from obi-one)

```json
[
  {
    "id": "soma",
    "parent_id": null,
    "type": 0,
    "points": [[x, y, z], ...],
    "radii": [r, ...]
  },
  {
    "id": "section_1",
    "parent_id": "soma",
    "type": 3,
    "points": [[x, y, z], ...],
    "radii": [r, ...]
  }
]
```

Section types: 0=Soma, 1=Dendrite, 2=BasalDendrite, 3=ApicalDendrite, 4=Myelin, 5=Axon.

## Template 3: Large Circuit (somas only)

For circuits with hundreds+ neurons, use `MorphoViewerSomasOnly` which renders only soma spheres (no morphology loading needed).

```html
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Circuit Viewer (Somas)</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body { width: 100vw; height: 100vh; overflow: hidden; }
    #root { width: 100%; height: 100%; }
  </style>
</head>
<body>
  <div id="root"></div>
  <script type="importmap">
  {
    "imports": {
      "react": "https://esm.sh/react@19.1.0",
      "react-dom/client": "https://esm.sh/react-dom@19.1.0/client",
      "@openbraininstitute/morphoviewer": "https://esm.sh/@openbraininstitute/morphoviewer@0.32.1?external=react"
    }
  }
  </script>
  <script type="module">
    import React from 'react';
    import { createRoot } from 'react-dom/client';
    import { MorphoViewerSomasOnly, MorphoViewerSignals } from '@openbraininstitute/morphoviewer';

    // === INLINED DATA ===
    // Array of {position: [x,y,z], morphologyId: string}
    const nodes = __NODES_JSON__;

    const cellInfos = nodes.map((node, i) => ({
      morphologyId: node.morphologyId || `cell-${i}`,
      position: node.position,
      color: '#4a90d9',
    }));

    const signals = new MorphoViewerSignals();

    function App() {
      return React.createElement(MorphoViewerSomasOnly, {
        somaRadius: 8,
        gizmo: true,
        scalebar: { length: 100, label: '100 μm', color: '#ffffff' },
        cellInfos,
        backgroundColor: '#1a1a1a',
        signals,
        controls: [],
      });
    }

    createRoot(document.getElementById('root')).render(React.createElement(App));
  </script>
</body>
</html>
```

### Data for large circuits

For large circuits, nodes come from obi-one's endpoint with positions but no morphology loading:
```
GET /api/obi-one/circuit/viz/{circuit_id}/nodes
```

Only `position` is needed. No per-cell morphology fetch.

## Guidelines for Data Size

| Circuit scale | Component | Data to inline | Typical size |
|--------------|-----------|----------------|--------------|
| Single morphology | `MorphologyCanvas` | SWC text | 50KB–2MB |
| Pair (2–5 neurons) | `MorphoViewerSmallCircuit` | Nodes + morphologies | 200KB–5MB |
| Small microcircuit (5–50) | `MorphoViewerSmallCircuit` | Nodes + morphologies | 2–20MB |
| Large circuit (50–1000+) | `MorphoViewerSomasOnly` | Node positions only | 10–100KB |

For circuits >50 neurons, prefer `MorphoViewerSomasOnly` to keep file size manageable.

## Workflow for Claude

1. User asks to visualize a morphology or circuit
2. Fetch the data using the appropriate API endpoint (EntityCore for SWC, obi-one for circuits)
3. Choose the appropriate template based on what's being visualized
4. Inline the data into the template
5. Write the HTML file to disk (e.g., `/tmp/viewer.html` or `~/Desktop/viewer.html`)
6. Open it: `open <path>` (macOS) or `xdg-open <path>` (Linux)

## Interaction Controls (all templates)

- **Scroll/pinch** — zoom
- **Left-drag** — rotate (orbit)
- **Ctrl+drag / right-drag** — pan
- **Gizmo** (corner cube) — click face to snap to axis view

## CDN URLs

```
https://esm.sh/@openbraininstitute/morphoviewer@0.32.1
https://esm.sh/react@19.1.0
https://esm.sh/react-dom@19.1.0/client
```

Use `?external=react` on the morphoviewer import when using import maps to avoid duplicate React instances.

---

## Working directory

When the visualization is part of a scientific session on the sandbox, write the generated page under that conversation's topic directory (per [[obi-logbook]]) rather than to `/tmp` or `~/Desktop` as the workflow above suggests:

```
/home/jovyan/<topic>/
└── plots/
    └── <what-it-shows>.html      ← alongside the session's other figures
```

The viewer page is a figure — it belongs in `plots/` with the rest, named for what it shows. `/tmp` is ephemeral overlay storage and will not survive the session. For a standalone one-off visualization with no scientific session around it, writing locally and opening it directly is fine.

## Logbook

When the visualization is part of a scientific session (rather than a one-off "show me this cell"), log it per [[obi-logbook]] — read it for the location, format, and content rules. A figure with no record of what it shows is not a result.

Record:

- **What is shown** — which morphology or circuit, by name: cell type, brain region, species, and for circuits the neuron count and populations included.
- **Why it was visualized** — the question the picture is meant to answer (checking a reconstruction, comparing cell types, inspecting circuit layout before simulation).
- **What was rendered and what was left out** — somas-only vs. full morphologies, any subsampling of the circuit, and the scientific consequence of that choice (e.g. "somas only, so dendritic overlap between layers is not assessable here").
- **What it shows** — one or two sentences of actual observation, not just "a viewer was generated".
- **Output** — the path of the HTML page, alongside the other session outputs.
- **Provenance** — the EntityCore IDs of the morphology/circuit rendered.

Do **not** log the fetch endpoints, CDN URLs, template choice, or file-size mechanics — see the "What never goes in" list in [[obi-logbook]].

## Linking

**Link everything.** Per [[obi-links]], the rendered entity and the generated page both go out as hyperlinks — a bare UUID or a bare path is a defect, not a style choice. `{domain}` is `staging.openbraininstitute.org` on staging, `www.openbraininstitute.org` on production, and must match the environment the data was fetched from.

- **The generated page** — when it is written on the OBI sandbox: take the `download_url` from `{obi}:get-sandbox-download-url` and swap `/files/` for `/lab/tree/`, keeping the rest of the path (`home/jovyan` included). Note that JupyterLab opens an `.html` file in an editor tab, not as a rendered page — so the link is for locating and downloading it; to actually *show* the viewer, bridge the file to the user as usual ([[chat-obi-sandbox-bridge]]) and hand over the link alongside it, not instead of it.
- **What is being visualized** — `https://{domain}/app/entity/{id}` for the morphology or circuit rendered, so the user can reach its detail page from the same reply.
- **Jobs** — generating a viewer page launches nothing, so there is no workflows activity link here.
