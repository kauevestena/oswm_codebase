import { collectViewportStats } from "./snapshot_stats.js";
import { renderSummaryChart } from "./snapshot_charts.js";

const EXPORT_WIDTH = 1500;
const EXPORT_HEIGHT = 930;
const EXPORT_TIMEOUT_MS = 25000;

function escapeHtml(value) {
    return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}

function formatNumber(value, digits = 1) {
    if (value === null || value === undefined || !Number.isFinite(Number(value))) return "—";
    return new Intl.NumberFormat(undefined, { maximumFractionDigits: digits }).format(Number(value));
}

function formatPercent(value) {
    return `${formatNumber(value, 1)}%`;
}

export function normalizeBounds(bounds) {
    if (!bounds) throw new Error("Snapshot extent is unavailable.");
    if (typeof bounds.getWest === "function") {
        return [[bounds.getWest(), bounds.getSouth()], [bounds.getEast(), bounds.getNorth()]];
    }
    if (Array.isArray(bounds) && bounds.length === 4) {
        return [[Number(bounds[0]), Number(bounds[1])], [Number(bounds[2]), Number(bounds[3])]];
    }
    if (Array.isArray(bounds) && bounds.length === 2 && bounds.every(Array.isArray)) {
        return bounds.map((corner) => corner.map(Number));
    }
    throw new Error("Snapshot extent has an unsupported format.");
}

export function stripRasterBasemap(style) {
    const vectorStyle = JSON.parse(JSON.stringify(style));
    const rasterSources = new Set(
        Object.entries(vectorStyle.sources || {})
            .filter(([, source]) => source.type === "raster" || source.type === "raster-dem")
            .map(([sourceId]) => sourceId),
    );
    vectorStyle.layers = (vectorStyle.layers || []).filter(
        (layer) => layer.type !== "raster" && !rasterSources.has(layer.source),
    );
    rasterSources.forEach((sourceId) => delete vectorStyle.sources[sourceId]);
    delete vectorStyle.terrain;
    return vectorStyle;
}

export function computeScaleBar(latitude, zoom, targetPixels = 120) {
    const earthCircumference = 40075016.686;
    const metersPerPixel = (
        earthCircumference * Math.cos((Number(latitude) * Math.PI) / 180)
    ) / (512 * (2 ** Number(zoom)));
    const rawDistance = Math.max(metersPerPixel * targetPixels, 0.001);
    const magnitude = 10 ** Math.floor(Math.log10(rawDistance));
    const normalized = rawDistance / magnitude;
    const niceFactor = normalized >= 5 ? 5 : normalized >= 2 ? 2 : 1;
    const meters = niceFactor * magnitude;
    return {
        meters,
        widthPixels: meters / metersPerPixel,
        label: meters >= 1000
            ? `${formatNumber(meters / 1000, 2)} km`
            : `${formatNumber(meters, 0)} m`,
    };
}

function waitForIdle(map, timeoutMs = EXPORT_TIMEOUT_MS) {
    return new Promise((resolve, reject) => {
        let settled = false;
        const finish = (callback, value) => {
            if (settled) return;
            settled = true;
            clearTimeout(timer);
            callback(value);
        };
        const timer = setTimeout(
            () => finish(reject, new Error("Timed out while waiting for map tiles.")),
            timeoutMs,
        );
        map.once("idle", () => finish(resolve));
        try {
            if (map.isStyleLoaded?.() && map.areTilesLoaded?.()) finish(resolve);
        } catch (_error) {
            // The idle listener remains authoritative while the style initializes.
        }
    });
}

async function nextFrame() {
    await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
}

async function renderExportMap(maplibregl, style, bounds) {
    const container = document.createElement("div");
    container.className = "oswm-snapshot-export-map";
    container.style.width = `${EXPORT_WIDTH}px`;
    container.style.height = `${EXPORT_HEIGHT}px`;
    document.body.appendChild(container);
    let exportMap;
    try {
        exportMap = new maplibregl.Map({
            container,
            style,
            bounds,
            fitBoundsOptions: { padding: 24, duration: 0 },
            bearing: 0,
            pitch: 0,
            interactive: false,
            attributionControl: false,
            pixelRatio: 2,
            canvasContextAttributes: {
                antialias: true,
                preserveDrawingBuffer: true,
            },
            fadeDuration: 0,
        });
        await waitForIdle(exportMap);
        exportMap.resize();
        await nextFrame();
        const canvas = exportMap.getCanvas();
        if (!canvas.width || !canvas.height) throw new Error("The export map canvas is empty.");
        const imageUrl = canvas.toDataURL("image/png");
        if (!imageUrl || imageUrl.length < 1000) throw new Error("The export map image is blank.");
        return {
            imageUrl,
            scale: computeScaleBar(exportMap.getCenter().lat, exportMap.getZoom()),
        };
    } finally {
        if (exportMap) exportMap.remove();
        container.remove();
    }
}

async function captureMap(map, bounds) {
    const style = JSON.parse(JSON.stringify(map.getStyle()));
    try {
        return await renderExportMap(window.maplibregl, style, bounds);
    } catch (primaryError) {
        try {
            const fallback = await renderExportMap(
                window.maplibregl,
                stripRasterBasemap(style),
                bounds,
            );
            return {
                ...fallback,
                warning: "The external basemap could not be captured; this print uses OSWM vector data only.",
            };
        } catch (fallbackError) {
            throw new Error(
                `Map rendering failed (${primaryError.message}; fallback: ${fallbackError.message}).`,
            );
        }
    }
}

function categoricalFacts(summary) {
    const dominant = summary.dominant
        ? `${escapeHtml(summary.dominant.value)} (${formatPercent(summary.dominant.percent)} of known)`
        : "—";
    const lengthFacts = summary.totalLengthKm === undefined ? "" : `
            <div><dt>Mapped line length</dt><dd>${formatNumber(summary.totalLengthKm, 2)} km</dd></div>
            <div><dt>Length without value</dt><dd>${formatNumber(summary.unknownLengthKm, 2)} km</dd></div>`;
    return `
        <dl class="oswm-snapshot-facts">
            <div><dt>Unique elements</dt><dd>${formatNumber(summary.total, 0)}</dd></div>
            <div><dt>Known values</dt><dd>${formatNumber(summary.known, 0)}</dd></div>
            <div><dt>Unknown / missing</dt><dd>${formatNumber(summary.unknown, 0)} (${formatPercent(summary.unknownPercent)})</dd></div>
            <div><dt>Known categories</dt><dd>${formatNumber(summary.knownCategoryCount, 0)}</dd></div>
            <div><dt>Dominant category</dt><dd>${dominant}</dd></div>
            <div><dt>Shannon entropy</dt><dd>${formatNumber(summary.shannonEntropy, 3)}</dd></div>
            <div><dt>Effective diversity</dt><dd>${formatNumber(summary.effectiveDiversity, 2)}</dd></div>
            ${lengthFacts}
        </dl>`;
}

function numericFacts(summary) {
    return `
        <dl class="oswm-snapshot-facts">
            <div><dt>Unique elements</dt><dd>${formatNumber(summary.total, 0)}</dd></div>
            <div><dt>Valid values</dt><dd>${formatNumber(summary.known, 0)}</dd></div>
            <div><dt>Unknown / missing</dt><dd>${formatNumber(summary.unknown, 0)} (${formatPercent(summary.unknownPercent)})</dd></div>
            <div><dt>Invalid / n.a.</dt><dd>${formatNumber(summary.invalid, 0)}</dd></div>
            <div><dt>Median</dt><dd>${formatNumber(summary.median, 2)}</dd></div>
            <div><dt>Range</dt><dd>${formatNumber(summary.min, 2)} – ${formatNumber(summary.max, 2)}</dd></div>
        </dl>`;
}

function renderFacts(summary) {
    if (summary.kind === "multi") {
        return summary.panels.map((panel) => `
            <section class="oswm-snapshot-fact-panel">
                <h3>${escapeHtml(panel.label)}</h3>
                ${panel.kind === "numeric" ? numericFacts(panel) : categoricalFacts(panel)}
            </section>`).join("");
    }
    return summary.kind === "numeric" ? numericFacts(summary) : categoricalFacts(summary);
}

function renderCharts(summary, theme) {
    if (summary.kind === "multi") {
        return summary.panels.map((panel, index) => (
            renderSummaryChart(panel, theme.panels[index] || panel, { width: 560, rowHeight: 28 })
        )).join("");
    }
    return renderSummaryChart(summary, theme, { width: 560, rowHeight: 28 });
}

function legendEntries(summary, theme) {
    if (summary.kind === "numeric") {
        const entries = (summary.bins || []).map((bin) => ({ label: bin.label, color: bin.color }));
        if (summary.invalid) entries.push({ label: "Invalid / n.a.", color: theme.invalid?.color || "#808080" });
        if (summary.unknown) entries.push({ label: "Unknown / missing", color: theme.unknown_color || "#636363" });
        return entries;
    }
    const entries = (summary.categories || []).slice(0, 12).map((category) => ({
        label: category.value,
        color: category.color,
    }));
    if (summary.unknown) entries.push({ label: "Unknown / missing", color: theme.unknown_color || "#636363" });
    return entries;
}

function renderLegendBlock(summary, theme) {
    const entries = legendEntries(summary, theme);
    return `<section class="oswm-snapshot-legend-block">
        <h3>${escapeHtml(theme.label)}</h3>
        <div class="oswm-snapshot-legend-items">
            ${entries.map((entry) => `<span><i style="--legend-color:${escapeHtml(entry.color)}"></i>${escapeHtml(entry.label)}</span>`).join("")}
            ${entries.length ? "" : "<em>No classified features in this scope.</em>"}
        </div>
    </section>`;
}

function renderLegend(summary, theme) {
    if (summary.kind === "multi") {
        return summary.panels.map((panel, index) => (
            renderLegendBlock(panel, theme.panels[index] || panel)
        )).join("");
    }
    return renderLegendBlock(summary, theme);
}

function boundsText(bounds) {
    const [[west, south], [east, north]] = bounds;
    return `W ${west.toFixed(5)} · S ${south.toFixed(5)} · E ${east.toFixed(5)} · N ${north.toFixed(5)}`;
}

function sheetMarkup({ title, nodeName, theme, summary, scope, bounds, capture, generatedAt }) {
    const scopeLabel = scope === "node" ? "Whole node" : "Current viewport";
    const timestamp = generatedAt
        ? new Date(generatedAt).toLocaleString()
        : new Date().toLocaleString();
    const sourceNote = scope === "node"
        ? "Exact node aggregation from processed GeoParquet."
        : "Counts are deduplicated visible OSM elements; tiled geometry lengths are not estimated.";
    return `<article class="oswm-snapshot-print-sheet">
        <header class="oswm-snapshot-sheet-header">
            <div>
                <p class="oswm-snapshot-kicker">OSWM scrutiny map</p>
                <h1>${escapeHtml(title)}</h1>
            </div>
            <dl>
                <div><dt>Node</dt><dd>${escapeHtml(nodeName)}</dd></div>
                <div><dt>Theme</dt><dd>${escapeHtml(theme.label)}</dd></div>
                <div><dt>Scope</dt><dd>${scopeLabel}</dd></div>
                <div><dt>Generated</dt><dd>${escapeHtml(timestamp)}</dd></div>
            </dl>
        </header>
        <div class="oswm-snapshot-sheet-grid">
            <section class="oswm-snapshot-map-column">
                <div class="oswm-snapshot-map-frame">
                    <img src="${capture.imageUrl}" alt="Map for the selected scrutiny extent" class="oswm-snapshot-map-image">
                    <div class="oswm-snapshot-north" aria-label="North"><span>▲</span>N</div>
                    <div class="oswm-snapshot-scale" style="--scale-width:${capture.scale.widthPixels}px">
                        <span></span><b>${escapeHtml(capture.scale.label)}</b>
                    </div>
                </div>
                <p class="oswm-snapshot-extent">${escapeHtml(boundsText(bounds))}</p>
                ${capture.warning ? `<p class="oswm-snapshot-warning">${escapeHtml(capture.warning)}</p>` : ""}
            </section>
            <aside class="oswm-snapshot-analysis-column">
                <section class="oswm-snapshot-analysis-block">
                    <h2>Scrutiny facts</h2>
                    ${renderFacts(summary)}
                </section>
                <section class="oswm-snapshot-analysis-block oswm-snapshot-chart-block">
                    ${renderCharts(summary, theme)}
                </section>
                <section class="oswm-snapshot-analysis-block oswm-snapshot-legend">
                    <h2>Legend</h2>
                    ${renderLegend(summary, theme)}
                </section>
            </aside>
        </div>
        <footer>
            <span>${escapeHtml(sourceNote)}</span>
            <span>Data © OpenStreetMap contributors · Basemap © CARTO · OpenSidewalkMap</span>
        </footer>
    </article>`;
}

export class SnapshotComposer {
    constructor(map, params, options = {}) {
        this.map = map;
        this.params = params;
        this.getActiveStyleKey = options.getActiveStyleKey || (() => "footway_categories");
        this.root = null;
        this.summaryCache = null;
        this.renderToken = 0;
        this.keyHandler = (event) => {
            if (event.key === "Escape") this.close();
        };
    }

    build() {
        if (this.root) return;
        this.root = document.createElement("div");
        this.root.className = "oswm-snapshot-backdrop is-hidden";
        this.root.setAttribute("role", "dialog");
        this.root.setAttribute("aria-modal", "true");
        this.root.setAttribute("aria-labelledby", "oswm-snapshot-dialog-title");
        this.root.innerHTML = `
            <section class="oswm-snapshot-modal">
                <header class="oswm-snapshot-modal-header">
                    <div>
                        <p>Printable Webmap snapshot</p>
                        <h2 id="oswm-snapshot-dialog-title">Create scrutiny map</h2>
                    </div>
                    <button type="button" class="oswm-snapshot-close" aria-label="Close snapshot composer">×</button>
                </header>
                <form class="oswm-snapshot-options" onsubmit="return false">
                    <label>Title<input name="title" type="text" maxlength="100"></label>
                    <label>Scope<select name="scope"><option value="viewport">Current viewport</option><option value="node">Whole node</option></select></label>
                    <span class="oswm-snapshot-format">A4 · Landscape · North-up</span>
                    <button type="button" data-action="update">Update preview</button>
                </form>
                <div class="oswm-snapshot-status" role="status" aria-live="polite"></div>
                <main class="oswm-snapshot-preview"></main>
                <footer class="oswm-snapshot-actions">
                    <button type="button" data-action="cancel" class="secondary">Cancel</button>
                    <button type="button" data-action="print" disabled>Print / Save as PDF</button>
                </footer>
            </section>`;
        document.body.appendChild(this.root);
        this.root.querySelector(".oswm-snapshot-close").addEventListener("click", () => this.close());
        this.root.querySelector('[data-action="cancel"]').addEventListener("click", () => this.close());
        this.root.querySelector('[data-action="update"]').addEventListener("click", () => this.updatePreview());
        this.root.querySelector('[data-action="print"]').addEventListener("click", () => this.print());
        this.root.querySelector('[name="scope"]').addEventListener("change", () => this.updatePreview());
        this.root.querySelector('[name="title"]').addEventListener("input", (event) => {
            const heading = this.root.querySelector(".oswm-snapshot-print-sheet h1");
            if (heading) heading.textContent = event.target.value || this.defaultTitle();
        });
    }

    activeTheme() {
        const styleKey = this.getActiveStyleKey();
        const configured = this.params.snapshot?.themes?.[styleKey];
        if (configured) return configured;
        return {
            id: styleKey,
            kind: "categorical",
            label: this.params.styles?.[styleKey]?.name || styleKey,
            attribute: "__layer__",
            layers: this.params.data_layers || [],
            colors: {},
            unknown_value: "?",
            unknown_color: "#636363",
        };
    }

    defaultTitle() {
        return `${this.activeTheme().label} — scrutiny map`;
    }

    async open() {
        this.build();
        this.root.classList.remove("is-hidden");
        document.body.classList.add("oswm-snapshot-modal-open");
        document.addEventListener("keydown", this.keyHandler);
        const titleInput = this.root.querySelector('[name="title"]');
        titleInput.value = this.defaultTitle();
        this.root.querySelector('[name="scope"]').value = this.params.snapshot?.default_scope || "viewport";
        this.root.querySelector(".oswm-snapshot-close").focus();
        await this.updatePreview();
    }

    close() {
        if (!this.root) return;
        this.renderToken += 1;
        this.root.classList.add("is-hidden");
        document.body.classList.remove("oswm-snapshot-modal-open");
        document.removeEventListener("keydown", this.keyHandler);
    }

    destroy() {
        this.close();
        this.root?.remove();
        this.root = null;
    }

    async nodeSummary(themeId) {
        if (!this.summaryCache) {
            const response = await fetch(this.params.snapshot.summary_url, { cache: "no-store" });
            if (!response.ok) throw new Error(`Node summary is unavailable (HTTP ${response.status}).`);
            this.summaryCache = await response.json();
        }
        const summary = this.summaryCache.themes?.[themeId];
        if (!summary) throw new Error(`No whole-node summary exists for theme “${themeId}”.`);
        return { summary, generatedAt: this.summaryCache.generated_at };
    }

    async updatePreview() {
        if (!this.root || this.root.classList.contains("is-hidden")) return;
        const token = ++this.renderToken;
        const status = this.root.querySelector(".oswm-snapshot-status");
        const preview = this.root.querySelector(".oswm-snapshot-preview");
        const printButton = this.root.querySelector('[data-action="print"]');
        const updateButton = this.root.querySelector('[data-action="update"]');
        printButton.disabled = true;
        updateButton.disabled = true;
        status.textContent = "Preparing statistics and high-resolution map…";
        preview.innerHTML = '<div class="oswm-snapshot-loading">Rendering preview…</div>';

        try {
            await waitForIdle(this.map, 15000);
            const theme = this.activeTheme();
            const scope = this.root.querySelector('[name="scope"]').value;
            const bounds = normalizeBounds(scope === "node" ? this.params.bounds : this.map.getBounds());
            let summary;
            let generatedAt;
            if (scope === "node") {
                ({ summary, generatedAt } = await this.nodeSummary(theme.id));
            } else {
                summary = collectViewportStats(this.map, theme);
            }
            const capture = await captureMap(this.map, bounds);
            if (token !== this.renderToken) return;
            const title = this.root.querySelector('[name="title"]').value || this.defaultTitle();
            preview.innerHTML = sheetMarkup({
                title,
                nodeName: this.params.snapshot?.node_name || "OSWM node",
                theme,
                summary,
                scope,
                bounds,
                capture,
                generatedAt,
            });
            status.textContent = capture.warning || "Preview ready. Unknown values are reported separately from diversity.";
            printButton.disabled = false;
        } catch (error) {
            if (token !== this.renderToken) return;
            preview.innerHTML = `<div class="oswm-snapshot-error"><strong>Snapshot could not be prepared.</strong><p>${escapeHtml(error.message)}</p></div>`;
            status.textContent = "Rendering failed; no blank document will be printed.";
        } finally {
            if (token === this.renderToken) updateButton.disabled = false;
        }
    }

    print() {
        if (!this.root?.querySelector(".oswm-snapshot-print-sheet")) return;
        const previousTitle = document.title;
        const requestedTitle = this.root.querySelector('[name="title"]').value || this.defaultTitle();
        const restore = () => {
            document.title = previousTitle;
            document.body.classList.remove("oswm-snapshot-printing");
        };
        document.title = requestedTitle;
        document.body.classList.add("oswm-snapshot-printing");
        window.addEventListener("afterprint", restore, { once: true });
        window.print();
        setTimeout(restore, 1000);
    }
}
