import assert from "node:assert/strict";
import { after, before, test } from "node:test";
import { readFile, mkdtemp, writeFile, rm } from "node:fs/promises";
import { createRequire } from "node:module";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import { installThemeChartControl } from "./theme_chart_control.js";

const require = createRequire(import.meta.url);
let echarts;
let rendererDirectory;
before(async () => {
    // Exercise the exact upstream artifact selected by the production template,
    // without depending on a CDN during CI. +esm is a CDN transformation, not a
    // shipped artifact: it duplicates ZRender classes and silently paints no SVG.
    const template = await readFile(new URL("../webmap_base.html", import.meta.url), "utf8");
    const specifier = template.match(/loadECharts:\s*\(\)\s*=>\s*import\('([^']+)'\)/)?.[1];
    const url = new URL(specifier);
    const artifact = url.pathname.match(/^\/npm\/echarts@([^/]+)\/(dist\/echarts\.esm\.min\.js)$/);
    assert.ok(artifact, "Load the official, self-contained ECharts ESM distribution");
    assert.equal(artifact[1], require("echarts/package.json").version);
    const source = await readFile(require.resolve(`echarts/${artifact[2]}`), "utf8");
    // The upstream package declares CommonJS; use .mjs to evaluate its unchanged
    // browser ESM bytes as ESM in Node, rather than testing a different build.
    rendererDirectory = await mkdtemp(join(tmpdir(), "oswm-chart-test-"));
    const modulePath = join(rendererDirectory, "echarts.mjs");
    await writeFile(modulePath, source);
    echarts = await import(pathToFileURL(modulePath));
});
after(async () => {
    if (rendererDirectory) await rm(rendererDirectory, { recursive: true, force: true });
});

// Only the control's DOM shell is simulated. Chart layout and SVG painting use
// real ECharts with fixed SSR dimensions, independent of WebGL/canvas support.
class Element {
    constructor(tag) {
        this.tagName = tag;
        this.children = [];
        this.attributes = new Map();
        this.listeners = new Map();
        this.style = {};
        this.classList = { add() {}, remove() {} };
        this.text = "";
    }
    set textContent(value) { this.text = value; this.children = []; }
    get textContent() { return this.text + this.children.map((c) => c.textContent).join(" "); }
    append(...children) { this.children.push(...children); }
    appendChild(child) { this.append(child); }
    replaceChildren(...children) { this.text = ""; this.children = children; }
    setAttribute(name, value) { this.attributes.set(name, value); }
    removeAttribute(name) { this.attributes.delete(name); }
    addEventListener(name, callback) { this.listeners.set(name, callback); }
    // Let ECharts use its built-in text metrics fallback, as in headless SSR.
    getContext() { return null; }
    focus() {}
    remove() {}
}

const config = {
    summary_url: "data/snapshots/node_summary.json",
    default_scope: "node",
    themes: {
        categories: {
            id: "categories", kind: "categorical", label: "Footway Categories",
            attribute: "__layer__", layers: ["sidewalks", "crossings", "missing"],
            measure: "count", colors: { sidewalks: "steelblue", crossings: "orange" },
        },
        age: {
            id: "age", kind: "numeric", label: "Update age", attribute: "age",
            layers: ["sidewalks"], measure: "count", breaks: [0, 2, 4],
            colors: ["green", "orange", "red"],
        },
    },
};
const nodeSummary = {
    generated_at: "2026-10-01T00:33:44Z",
    themes: {
        categories: {
            kind: "categorical", total: 100, unknown: 0,
            categories: [
                { value: "sidewalks", count: 80, color: "steelblue" },
                { value: "crossings", count: 20, color: "orange" },
            ],
        },
    },
};
function feature(id, age = 1) {
    return {
        id, sourceLayer: "sidewalks", layer: { id: "sidewalks" },
        properties: { id, element: "way", age },
        geometry: { type: "LineString", coordinates: [[0, 0], [0.01, 0]] },
    };
}
const settle = () => new Promise(setImmediate);

function setup(t) {
    const restoreGlobals = [];
    for (const [name, value] of Object.entries({
        document: { createElement: (tag) => new Element(tag) },
        window: { addEventListener() {}, removeEventListener() {}, matchMedia: () => ({ matches: true }) },
        ResizeObserver: class { observe() {} disconnect() {} },
    })) {
        const previous = Object.getOwnPropertyDescriptor(globalThis, name);
        Object.defineProperty(globalThis, name, { configurable: true, value });
        restoreGlobals.push(() => previous
            ? Object.defineProperty(globalThis, name, previous)
            : delete globalThis[name]);
    }
    let requests = 0;
    let imports = 0;
    let queries = 0;
    const handlers = new Map();
    const map = {
        features: [feature(1), feature(1)],
        loaded: true,
        addControl(control) { control.onAdd(this); },
        on(event, callback) { handlers.set(event, callback); },
        off(event) { handlers.delete(event); },
        fire(event) { handlers.get(event)?.(); },
        isStyleLoaded() { return this.loaded; },
        getLayer: (id) => id !== "missing",
        getLayoutProperty: (id) => id === "crossings" ? "none" : "visible",
        getBounds: () => [-1, -1, 1, 1],
        queryRenderedFeatures({ layers }) {
            queries += 1;
            assert.deepEqual(layers, ["sidewalks"]);
            return this.features;
        },
    };
    t.mock.method(globalThis, "fetch", async (url) => {
        requests += 1;
        assert.equal(url, config.summary_url);
        return { ok: true, json: async () => nodeSummary };
    });
    const control = installThemeChartControl(map, config, {
        getActiveStyleKey: () => "categories",
        loadECharts: async () => {
            imports += 1;
            return {
                init(_element, theme, options) {
                    assert.equal(options.renderer, "svg");
                    return echarts.init(null, theme, { ...options, ssr: true, width: 366, height: 300 });
                },
            };
        },
    });
    t.after(() => {
        control.onRemove();
        restoreGlobals.forEach((restore) => restore());
    });
    return { control, map, counts: () => ({ requests, imports, queries }) };
}

function assertPainted(chart, label) {
    const svg = chart.renderToSVGString();
    assert.match(svg, /<path\b/, "SVG must contain painted chart geometry, not just a background rect");
    assert.match(svg, /<text\b/, "SVG must contain axis labels");
    assert.ok(svg.includes(label), `SVG must display ${label}`);
}

test("whole-dataset control paints the exact summary and never queries rendered tiles", async (t) => {
    const { control, counts } = setup(t);
    control.open();
    await settle();
    assert.match(control.status.textContent, /Entire dataset · exact/);
    assert.equal(control.content.attributes.has("aria-busy"), false);
    assert.equal(control.charts.length, 1);
    assertPainted(control.charts[0], "sidewalks");
    assert.deepEqual(control.charts[0].getOption().series[0].data.map((d) => d.value), [80, 20]);
    assert.match(control.content.textContent, /100 features represented/);
    assert.match(control.content.textContent, /80 features/);
    assert.deepEqual(counts(), { requests: 1, imports: 1, queries: 0 });
});

test("visible-area control paints deduplicated live data, refreshes on move and returns to exact scope", async (t) => {
    const { control, map, counts } = setup(t);
    t.mock.timers.enable({ apis: ["setTimeout"] });
    control.viewportInput.checked = true;
    control.open();
    await settle();
    assert.match(control.status.textContent, /Visible area · estimated/);
    assertPainted(control.charts[0], "sidewalks");
    assert.equal(control.charts[0].getOption().series[0].data[0].value, 1);
    assert.deepEqual(counts(), { requests: 0, imports: 1, queries: 1 });

    const previous = control.charts[0];
    map.features = [feature(1), feature(2), feature(3), feature(3)];
    map.fire("moveend");
    t.mock.timers.tick(100);
    await settle();
    assert.equal(previous.isDisposed(), true);
    assert.equal(control.charts[0].getOption().series[0].data[0].value, 3);
    assertPainted(control.charts[0], "sidewalks");
    assert.match(control.content.textContent, /3 features represented/);

    control.viewportInput.checked = false;
    control.viewportInput.listeners.get("change")();
    await settle();
    assert.match(control.status.textContent, /Entire dataset · exact/);
    assert.deepEqual(control.charts[0].getOption().series[0].data.map((d) => d.value), [80, 20]);
    assert.deepEqual(counts(), { requests: 1, imports: 1, queries: 2 });
});

test("live charts wait for style loading and repaint the newly selected numeric theme", async (t) => {
    const { control, map, counts } = setup(t);
    t.mock.timers.enable({ apis: ["setTimeout"] });
    map.loaded = false;
    control.viewportInput.checked = true;
    control.open();
    await settle();
    assert.match(control.status.textContent, /Waiting for the selected map style/);
    assert.equal(counts().queries, 0);
    map.features = [feature(1, 1), feature(2, 3)];
    control.setActiveStyle("age");
    map.loaded = true;
    map.fire("styledata");
    t.mock.timers.tick(180);
    await settle();
    assert.equal(control.title.textContent, "Update age");
    assertPainted(control.charts[0], "Features");
    assert.deepEqual(control.charts[0].getOption().series[0].data.map((d) => d.value), [1, 1, 0]);
    assert.equal(counts().requests, 0);
});
