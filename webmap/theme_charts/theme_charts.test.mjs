import assert from "node:assert/strict";
import test from "node:test";

import {
    collectViewportThemeStats,
    deduplicateRenderedFragments,
    lineLengthKmInBounds,
    normalizeMapBounds,
} from "./theme_chart_stats.js";
import {
    buildThemeChartOption,
    themeChartRows,
    themeMetricSummary,
} from "./theme_chart_options.js";

function lineFeature(id, value, coordinates, sourceLayer = "sidewalks") {
    return {
        id,
        sourceLayer,
        layer: { id: sourceLayer, "source-layer": sourceLayer },
        properties: { id, element: "way", surface: value },
        geometry: { type: "LineString", coordinates },
    };
}

test("map bounds normalize from MapLibre-like objects", () => {
    const bounds = normalizeMapBounds({
        getWest: () => -2,
        getSouth: () => -1,
        getEast: () => 3,
        getNorth: () => 4,
    });
    assert.deepEqual(bounds, { west: -2, south: -1, east: 3, north: 4 });
});

test("line measurement clips rendered fragments to the viewport", () => {
    const length = lineLengthKmInBounds(
        { type: "LineString", coordinates: [[-1, 0], [2, 0]] },
        [0, -1, 1, 1],
    );
    assert.ok(length > 111 && length < 112);
});

test("identical tile copies are removed while distinct fragments survive", () => {
    const first = lineFeature(1, "asphalt", [[0, 0], [0.01, 0]]);
    const secondFragment = lineFeature(1, "asphalt", [[0.01, 0], [0.02, 0]]);
    const fragments = deduplicateRenderedFragments([
        first,
        { ...first },
        secondFragment,
    ]);
    assert.equal(fragments.length, 2);
});

test("viewport line themes produce approximate length-weighted summaries", () => {
    const features = [
        lineFeature(1, "asphalt", [[0, 0], [0.01, 0]]),
        lineFeature(1, "asphalt", [[0, 0], [0.01, 0]]),
        lineFeature(2, "concrete", [[0, 0], [0.02, 0]]),
        lineFeature(3, "?", [[0, 0], [0.005, 0]]),
    ];
    const map = {
        getLayer: (id) => id === "sidewalks",
        getLayoutProperty: () => "visible",
        getBounds: () => [-0.1, -0.1, 0.1, 0.1],
        queryRenderedFeatures: ({ layers }) => {
            assert.deepEqual(layers, ["sidewalks"]);
            return features;
        },
    };
    const summary = collectViewportThemeStats(map, {
        id: "surface",
        kind: "categorical",
        label: "Surface",
        attribute: "surface",
        layers: ["sidewalks"],
        measure: "length",
        colors: { asphalt: "#f00", concrete: "#0f0", "?": "#333" },
        unknown_value: "?",
        unknown_color: "#333",
    });

    assert.equal(summary.total, 3);
    assert.equal(summary.estimated, true);
    assert.ok(summary.totalLengthKm > 3.8 && summary.totalLengthKm < 4.0);
    assert.ok(summary.lengthKmByCategory.concrete > summary.lengthKmByCategory.asphalt);
    assert.ok(summary.unknownLengthKm > 0.5);
});

test("length chart ordering uses represented length instead of feature count", () => {
    const summary = {
        kind: "categorical",
        total: 11,
        unknown: 1,
        categories: [
            { value: "concrete", count: 10, color: "#0f0" },
            { value: "asphalt", count: 1, color: "#f00" },
        ],
        totalLengthKm: 7,
        unknownLengthKm: 1,
        lengthKmByCategory: { concrete: 1, asphalt: 5 },
    };
    const theme = {
        label: "Surface",
        measure: "length",
        unknown_color: "#333",
    };
    const rows = themeChartRows(summary, theme);

    assert.deepEqual(rows.map((row) => row.label), [
        "asphalt",
        "concrete",
        "Unknown / missing",
    ]);
    assert.equal(rows[0].unit, "km");
    assert.equal(themeMetricSummary(summary, theme).value, 7);
});

test("numeric themes build a vertical histogram option", () => {
    const summary = {
        kind: "numeric",
        total: 5,
        known: 3,
        unknown: 1,
        invalid: 1,
        bins: [
            { label: "0–<2", count: 2, color: "#abc" },
            { label: "2+", count: 1, color: "#def" },
        ],
    };
    const theme = {
        label: "Update age",
        measure: "count",
        invalid: { color: "#888" },
        unknown_color: "#333",
    };
    const option = buildThemeChartOption(summary, theme, { reducedMotion: true });

    assert.equal(option.xAxis.type, "category");
    assert.equal(option.yAxis.type, "value");
    assert.equal(option.animationDuration, 0);
    assert.equal(option.series[0].data.length, 4);
});

test("multi themes query each configured vector-tile panel", () => {
    const map = {
        getLayer: () => true,
        getLayoutProperty: () => "visible",
        getBounds: () => [-1, -1, 1, 1],
        queryRenderedFeatures: ({ layers }) => (
            layers[0] === "crossings"
                ? [lineFeature(1, "marked", [[0, 0], [0.01, 0]], "crossings")]
                : []
        ),
    };
    const summary = collectViewportThemeStats(map, {
        id: "crossings_and_kerbs",
        kind: "multi",
        panels: [
            {
                id: "crossings",
                kind: "categorical",
                label: "Crossings",
                attribute: "surface",
                layers: ["crossings"],
                measure: "length",
                colors: {},
            },
            {
                id: "kerbs",
                kind: "categorical",
                label: "Kerbs",
                attribute: "kerb",
                layers: ["kerbs"],
                measure: "count",
                colors: {},
            },
        ],
    });

    assert.equal(summary.panels.length, 2);
    assert.equal(summary.panels[0].total, 1);
    assert.equal(summary.panels[1].total, 0);
});
