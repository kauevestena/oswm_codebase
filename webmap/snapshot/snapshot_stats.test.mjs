import assert from "node:assert/strict";
import test from "node:test";

import { categoricalChartRows, renderSummaryChart } from "./snapshot_charts.js";
import {
    collectViewportStats,
    deduplicateFeatures,
    featureIdentity,
    normalizeUnknown,
    summarizeCategoricalValues,
    summarizeNumericValues,
} from "./snapshot_stats.js";
import {
    computeScaleBar,
    normalizeAuthorPanel,
    normalizeBounds,
    stripRasterBasemap,
} from "./snapshot_composer.js";


function feature(sourceLayer, id, value, element = "way") {
    return {
        id,
        sourceLayer,
        layer: { id: sourceLayer },
        properties: { id, element, surface: value },
    };
}

test("tile fragments with one OSM identity are counted once", () => {
    const duplicate = feature("sidewalks", 42, "asphalt");
    const unique = deduplicateFeatures([duplicate, { ...duplicate }, feature("sidewalks", 43, "concrete")]);
    assert.equal(unique.length, 2);
});

test("equal IDs in different source layers remain distinct", () => {
    const unique = deduplicateFeatures([
        feature("sidewalks", 42, "asphalt"),
        feature("crossings", 42, "asphalt"),
    ]);
    assert.equal(unique.length, 2);
});

test("missing feature IDs receive stable per-result fallbacks", () => {
    const first = { sourceLayer: "sidewalks", properties: { surface: "asphalt" } };
    const second = { sourceLayer: "sidewalks", properties: { surface: "asphalt" } };
    assert.notEqual(featureIdentity(first, 0), featureIdentity(second, 1));
    assert.equal(deduplicateFeatures([first, second]).length, 2);
});

test("unknown spellings normalize into one incompleteness bucket", () => {
    assert.equal(normalizeUnknown(null), "?");
    assert.equal(normalizeUnknown(undefined), "?");
    assert.equal(normalizeUnknown(""), "?");
    assert.equal(normalizeUnknown("  "), "?");
    assert.equal(normalizeUnknown("?"), "?");
    assert.equal(normalizeUnknown(0), 0);
});

test("unknown values are excluded from Shannon diversity", () => {
    const summary = summarizeCategoricalValues(["a", "b", "?", null, ""]);
    assert.equal(summary.known, 2);
    assert.equal(summary.unknown, 3);
    assert.ok(Math.abs(summary.effectiveDiversity - 2) < 1e-6);
});

test("a single known category has entropy zero and effective diversity one", () => {
    const summary = summarizeCategoricalValues(["a", "a", "?"]);
    assert.equal(summary.shannonEntropy, 0);
    assert.equal(summary.effectiveDiversity, 1);
});

test("empty categorical input returns a valid empty result", () => {
    const summary = summarizeCategoricalValues([]);
    assert.deepEqual(
        { total: summary.total, known: summary.known, unknown: summary.unknown, categories: summary.categories },
        { total: 0, known: 0, unknown: 0, categories: [] },
    );
});

test("chart long-tail collapsing leaves analytical metrics untouched", () => {
    const values = ["a", "a", "b", "c", "d", "e"];
    const summary = summarizeCategoricalValues(values);
    const effectiveDiversity = summary.effectiveDiversity;
    const rows = categoricalChartRows(summary, { maxKnownRows: 2 });
    assert.equal(rows.at(-1).value, "Other known (3)");
    assert.equal(summary.effectiveDiversity, effectiveDiversity);
    assert.equal(summary.categories.length, 5);
});

test("numeric summaries follow configured class breaks", () => {
    const summary = summarizeNumericValues([null, -1, 0, 1.9, 2, 12], {
        breaks: [0, 2, 4, 10],
        colors: ["a", "b", "c", "d"],
        invalid: { operator: "<", threshold: 0 },
    });
    assert.equal(summary.unknown, 1);
    assert.equal(summary.invalid, 1);
    assert.deepEqual(summary.bins.map((bin) => bin.count), [2, 1, 0, 1]);
});

test("viewport collection queries only visible analytical layers and deduplicates", () => {
    const features = [
        feature("sidewalks", 1, "asphalt"),
        feature("sidewalks", 1, "asphalt"),
        feature("sidewalks", 2, "?"),
    ];
    const map = {
        getLayer: (id) => id === "sidewalks" || id === "hidden",
        getLayoutProperty: (id) => (id === "hidden" ? "none" : "visible"),
        queryRenderedFeatures: ({ layers }) => {
            assert.deepEqual(layers, ["sidewalks"]);
            return features;
        },
    };
    const summary = collectViewportStats(map, {
        id: "surface",
        kind: "categorical",
        label: "Surface",
        attribute: "surface",
        layers: ["sidewalks", "hidden"],
        colors: { asphalt: "#f00" },
        unknown_value: "?",
    });
    assert.equal(summary.total, 2);
    assert.equal(summary.known, 1);
    assert.equal(summary.unknown, 1);
});

test("SVG chart output remains vector and escaped", () => {
    const summary = summarizeCategoricalValues(["<unsafe>", "?"]);
    const svg = renderSummaryChart(summary, {
        label: "Surface & material",
        unknown_color: "#333",
    });
    assert.match(svg, /^<svg/);
    assert.match(svg, /Surface &amp; material/);
    assert.doesNotMatch(svg, /<unsafe>/);
});

test("composer helpers normalize extents, remove raster sources and make a scale", () => {
    assert.deepEqual(normalizeBounds([1, 2, 3, 4]), [[1, 2], [3, 4]]);
    const style = {
        version: 8,
        sources: { raster: { type: "raster" }, vector: { type: "vector" } },
        layers: [
            { id: "base", type: "raster", source: "raster" },
            { id: "data", type: "line", source: "vector" },
        ],
    };
    const stripped = stripRasterBasemap(style);
    assert.deepEqual(Object.keys(stripped.sources), ["vector"]);
    assert.deepEqual(stripped.layers.map((layer) => layer.id), ["data"]);
    const scale = computeScaleBar(-25.4, 15);
    assert.ok(scale.widthPixels > 0);
    assert.match(scale.label, /m|km/);
});

test("optional author panel is omitted unless title or content is present", () => {
    assert.deepEqual(normalizeAuthorPanel("  ", "\n"), {
        title: "",
        content: "",
        visible: false,
    });
    assert.deepEqual(normalizeAuthorPanel(" Field notes ", " <strong>Check</strong> "), {
        title: "Field notes",
        content: "<strong>Check</strong>",
        visible: true,
    });
});
