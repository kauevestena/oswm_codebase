# MapLibre GL JS v6 Migration Roadmap

## Overview
This document outlines the architectural changes and actionable tasks required to migrate the OpenSidewalkMap (OSWM) webmap and demo tools to **MapLibre GL JS v6**.

---

## Technical Context & Constraints

In **MapLibre GL v6**, the maintainers completely removed standard UMD bundle releases (`dist/maplibre-gl.js`) in favor of pure **ES Modules** (`dist/maplibre-gl.mjs`).

### Core Bottlenecks with Plain `<script>` Tags
1. **Module Execution Deferred**: `<script type="module">` tags execute asynchronously/deferred in standard browser environments.
2. **Legacy Plugin Conflicts**: Legacy third-party UMD plugins (such as `@watergis/maplibre-gl-legend`) expect `window.maplibregl` to exist synchronously at initial script evaluation time, causing `Uncaught ReferenceError: maplibregl is not defined`.

---

## Action Items & TODOs

### 1. Replace `@watergis/maplibre-gl-legend` (High Priority)
The current legend control (`@watergis/maplibre-gl-legend`) relies on legacy UMD script loading. It must be replaced with an ESM-compatible alternative or a native custom control.

#### Evaluated Candidates & Alternatives:
* **Option A: `maplibre-gl-components` (`@opengeos/maplibre-gl-components`)**
  - *Pros*: Full ESM support, actively maintained, includes categorical `Legend` and continuous `Colorbar` controls, clean TypeScript definitions.
  - *Usage*: `import { Legend } from "https://cdn.jsdelivr.net/npm/maplibre-gl-components@latest/+esm"`
* **Option B: `mapboxgl-legend`**
  - *Pros*: Light style-parsing legend control that supports MapLibre GL.
* **Option C: Native Custom OSWM Legend Control (`IControl`)**
  - *Pros*: Zero external dependencies, full layout control, seamless integration with OSWM's existing symbol iframe overlays (`map_symbols/*.html`).
  - *Implementation*: Implement MapLibre's `IControl` interface (`onAdd(map)`, `onRemove(map)`).

---

### 2. Update Core HTML Templates & Generator Scripts
- [ ] **[webmap_base.html](file:///home/kaue/opensidewalkmap_beta/oswm_codebase/webmap/webmap_base.html)**: Convert main script block to `<script type="module">` and import MapLibre GL v6:
  ```javascript
  import maplibregl from 'https://unpkg.com/maplibre-gl@6/dist/maplibre-gl.mjs';
  ```
- [ ] **[create_webmap_new.py](file:///home/kaue/opensidewalkmap_beta/oswm_codebase/webmap/create_webmap_new.py)**: Update template generation rules for ESM module imports.
- [ ] **[routing_demo.html](file:///home/kaue/opensidewalkmap_beta/oswm_codebase/routing/routing_demo.html)**: Migrate routing script tag to ESM import.

---

### 3. Update Dependency Imports to ESM
- [ ] **PMTiles**: Import PMTiles via ES module syntax:
  ```javascript
  import * as pmtiles from 'https://unpkg.com/pmtiles@latest/dist/pmtiles.js';
  ```
- [ ] **Turf.js & Path Finder**: Import ESM equivalents for `routing_demo.html`.

---

### 4. Verification & Testing
- [ ] Test PMTiles vector source protocol initialization under ES module scope.
- [ ] Verify snapshot composer (`snapshot_control.js`) with MapLibre v6 map instance.
- [ ] Test cross-browser compatibility on static GitHub Pages hosting.
