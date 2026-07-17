function escapeXml(value) {
    return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}

function truncate(value, length = 24) {
    const text = String(value);
    return text.length > length ? `${text.slice(0, length - 1)}…` : text;
}

export function categoricalChartRows(summary, options = {}) {
    const maxKnownRows = options.maxKnownRows || 7;
    const categories = summary.categories || [];
    const visible = categories.slice(0, maxKnownRows).map((category) => ({ ...category }));
    const tail = categories.slice(maxKnownRows);
    if (tail.length) {
        const count = tail.reduce((total, category) => total + category.count, 0);
        visible.push({
            value: `Other known (${tail.length})`,
            count,
            percent: summary.known ? (count / summary.known) * 100 : 0,
            color: "#a0a0a0",
        });
    }
    if (summary.unknown) {
        visible.push({
            value: "Unknown / missing",
            count: summary.unknown,
            percent: summary.unknownPercent,
            color: options.unknownColor || "#636363",
            unknown: true,
        });
    }
    return visible;
}

function renderRows(rows, title, options = {}) {
    const width = options.width || 560;
    const rowHeight = options.rowHeight || 30;
    const left = 160;
    const right = 66;
    const top = 34;
    const height = Math.max(92, top + rows.length * rowHeight + 18);
    const available = width - left - right;
    const maximum = Math.max(1, ...rows.map((row) => row.count));
    const bars = rows.map((row, index) => {
        const y = top + index * rowHeight;
        const barWidth = Math.max(row.count ? 2 : 0, (row.count / maximum) * available);
        const suffix = row.unknown ? " of all" : " of known";
        return `
            <text x="${left - 8}" y="${y + 15}" text-anchor="end" class="chart-label">${escapeXml(truncate(row.value))}</text>
            <rect x="${left}" y="${y}" width="${barWidth}" height="19" rx="2" fill="${escapeXml(row.color)}"></rect>
            <text x="${left + barWidth + 6}" y="${y + 15}" class="chart-value">${row.count} · ${Number(row.percent || 0).toFixed(1)}%${suffix}</text>`;
    }).join("");
    const emptyMessage = rows.length
        ? ""
        : `<text x="${width / 2}" y="62" text-anchor="middle" class="chart-empty">No features in this scope</text>`;

    return `<svg xmlns="http://www.w3.org/2000/svg" role="img" aria-label="${escapeXml(title)}" viewBox="0 0 ${width} ${height}" class="oswm-snapshot-chart">
        <style>
            .chart-title { font: 700 17px system-ui, sans-serif; fill: #172126; }
            .chart-label { font: 12px system-ui, sans-serif; fill: #26353c; }
            .chart-value { font: 11px system-ui, sans-serif; fill: #26353c; }
            .chart-empty { font: 13px system-ui, sans-serif; fill: #66757c; }
        </style>
        <text x="0" y="19" class="chart-title">${escapeXml(title)}</text>
        ${bars}${emptyMessage}
    </svg>`;
}

export function renderCategoricalChart(summary, theme, options = {}) {
    const rows = categoricalChartRows(summary, {
        ...options,
        unknownColor: theme.unknown_color,
    });
    return renderRows(rows, theme.label, options);
}

export function renderNumericChart(summary, theme, options = {}) {
    const rows = (summary.bins || []).map((bin) => ({
        value: bin.label,
        count: bin.count,
        percent: summary.known ? (bin.count / summary.known) * 100 : 0,
        color: bin.color,
    }));
    if (summary.invalid) {
        rows.push({
            value: "Invalid / not applicable",
            count: summary.invalid,
            percent: summary.total ? (summary.invalid / summary.total) * 100 : 0,
            color: theme.invalid?.color || "#808080",
            unknown: true,
        });
    }
    if (summary.unknown) {
        rows.push({
            value: "Unknown / missing",
            count: summary.unknown,
            percent: summary.unknownPercent,
            color: theme.unknown_color || "#636363",
            unknown: true,
        });
    }
    return renderRows(rows, theme.label, options);
}

export function renderSummaryChart(summary, theme, options = {}) {
    return summary.kind === "numeric"
        ? renderNumericChart(summary, theme, options)
        : renderCategoricalChart(summary, theme, options);
}
