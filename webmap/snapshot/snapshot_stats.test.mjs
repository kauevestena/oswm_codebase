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
    formatScaleLabel,
    normalizeAuthorPanel,
    normalizeBounds,
    renderSnapshotSheet,
    SnapshotComposer,
    stripRasterBasemap,
} from "./snapshot_composer.js";
import {
    createI18n,
    DEFAULT_LOCALE,
    resolveLocale,
    SUPPORTED_LOCALES,
} from "./snapshot_i18n.js";


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

test("snapshot locales are explicit, English-first and safely fall back to English", () => {
    assert.equal(DEFAULT_LOCALE, "en");
    assert.deepEqual(
        SUPPORTED_LOCALES.map((locale) => locale.code),
        ["en", "pt-BR", "es", "it", "fr", "de", "zh-CN", "ar"],
    );
    assert.equal(resolveLocale("unsupported"), "en");
    assert.equal(createI18n("unsupported").t("language"), "Language");
});

test("translations include localized theme labels and Arabic RTL metadata", () => {
    const portuguese = createI18n("pt-BR");
    assert.equal(portuguese.t("scrutinyFacts"), "Fatos para escrutínio");
    assert.equal(portuguese.themeLabel("surface", "Surface"), "Revestimento");

    const arabic = createI18n("ar");
    assert.equal(arabic.locale, "ar");
    assert.equal(arabic.direction, "rtl");
    assert.notEqual(arabic.t("legend"), "Legend");
});

test("every non-English locale translates the core composer and report labels", () => {
    const english = createI18n("en");
    const coreKeys = [
        "createScrutinyMap",
        "scope",
        "printSavePdf",
        "scrutinyFacts",
        "legend",
    ];
    for (const { code } of SUPPORTED_LOCALES.slice(1)) {
        const locale = createI18n(code);
        for (const key of coreKeys) {
            assert.notEqual(locale.t(key), english.t(key), `${code} must translate ${key}`);
        }
    }
});

test("localizing chart labels never translates source data values", () => {
    const summary = summarizeCategoricalValues([
        "asphalt",
        "asphalt",
        "paving_stones",
        "?",
    ]);
    const portuguese = createI18n("pt-BR");
    const rows = categoricalChartRows(summary, {
        unknownLabel: portuguese.t("unknownMissing"),
    });

    assert.ok(rows.some((row) => row.value === "asphalt"));
    assert.ok(rows.some((row) => row.value === "paving_stones"));
    assert.ok(rows.some((row) => row.value === "Desconhecido / ausente"));
    assert.ok(rows.filter((row) => row.dataValue).every((row) => (
        row.value === "asphalt" || row.value === "paving_stones"
    )));
});

test("scale units and numbers follow the selected output locale", () => {
    const arabic = createI18n("ar");
    assert.match(formatScaleLabel({ meters: 2000 }, arabic), /كم/);
    assert.equal(formatScaleLabel({ meters: 2000 }, createI18n("en")), "2 km");
});

test("the localized printable sheet preserves English category values", () => {
    const summary = summarizeCategoricalValues(["asphalt", "paving_stones", "?"]);
    const theme = {
        id: "surface",
        label: "Surface",
        unknown_color: "#636363",
    };
    const base = {
        title: "Field audit",
        nodeName: "Example node",
        theme,
        summary,
        scope: "viewport",
        bounds: [[-46.7, -23.6], [-46.6, -23.5]],
        capture: {
            imageUrl: "data:image/png;base64,example",
            scale: { meters: 200, widthPixels: 120 },
        },
        generatedAt: "2026-07-17T12:00:00Z",
        authorTitle: "",
        authorContent: "",
    };

    const portuguese = renderSnapshotSheet({ ...base, i18n: createI18n("pt-BR") });
    assert.match(portuguese, /lang="pt-BR" dir="ltr"/);
    assert.match(portuguese, /Fatos para escrutínio/);
    assert.match(portuguese, /<h2>Tema<\/h2>/);
    assert.match(portuguese, /asphalt/);
    assert.match(portuguese, /paving_stones/);
    assert.doesNotMatch(portuguese, /asfalto/);

    const arabic = renderSnapshotSheet({ ...base, i18n: createI18n("ar") });
    assert.match(arabic, /lang="ar" dir="rtl"/);
    assert.match(arabic, /asphalt/);
});

test("changing locale reuses the preview and preserves a custom title", () => {
    const titleInput = { value: "" };
    const localeSelect = { value: "en" };
    const status = { textContent: "" };
    const fields = new Map([
        ['[name="title"]', titleInput],
        ['[name="locale"]', localeSelect],
        [".oswm-snapshot-status", status],
    ]);
    const composer = new SnapshotComposer({}, {
        snapshot: {
            themes: {
                surface: { id: "surface", kind: "categorical", label: "Surface" },
            },
        },
    }, { getActiveStyleKey: () => "surface" });
    composer.root = {
        lang: "",
        dir: "",
        querySelector: (selector) => fields.get(selector),
        querySelectorAll: () => [],
    };
    let reusedPreview = 0;
    composer.renderLastSheet = () => {
        reusedPreview += 1;
        return true;
    };

    titleInput.value = composer.defaultTitle();
    composer.changeLocale("pt-BR");
    assert.equal(localeSelect.value, "pt-BR");
    assert.equal(titleInput.value, "Revestimento — mapa de escrutínio");
    assert.equal(reusedPreview, 1);

    titleInput.value = "Author-defined title";
    composer.changeLocale("ar");
    assert.equal(titleInput.value, "Author-defined title");
    assert.equal(composer.root.dir, "rtl");
    assert.equal(reusedPreview, 2);
});
