"""
OSWM Data Acquisition Runner
=============================
Discovers pedestrian-data projects on external project-management platforms
(HOT Tasking Manager, MapRoulette, Pic4Review), filters them by the node's
bounding box and polygon, and produces:

  - hub/acquisition/results.json   (structured index)
  - hub/acquisition/index.html     (interactive dashboard)

Usage:
    python generate_acquisition.py              # full run
    python generate_acquisition.py --dry-run    # print URLs, skip HTTP
    python generate_acquisition.py --keywords 6 # use first 6 keywords
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone

# Ensure the parent `datahub` directory is on sys.path so `dh_lib` can be imported
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dh_lib import (
    DEFAULT_ACQ_KEYWORDS_COUNT,
    CITY_NAME,
    ensure_parent_folder,
    acquisition_results_path,
    acquisition_page_path,
)
from acq_lib import (
    SEARCH_KEYWORDS,
    SUPPORTED_SERVICES,
    SERVICE_DISPATCH,
    get_bbox_from_boundary,
    get_boundary_polygon,
    query_to_json,
    deduplicate_results,
    filter_by_polygon,
    check_pic4review_online,
    fetch_project_bbox_from_detail,
)

# ---------------------------------------------------------------------------
# Collect projects from all services
# ---------------------------------------------------------------------------


def collect_all_projects(bbox, n_keywords=None, dry_run=False):
    """
    Fetch all projects from every supported service/instance, then filter
    locally by keyword matching.
    Returns (projects_list, service_status_dict).
    """
    # Since we now fetch all projects at once and filter locally,
    # default to using ALL keywords (no extra API cost per keyword)
    if n_keywords is None:
        n_keywords = len(SEARCH_KEYWORDS)

    keywords = SEARCH_KEYWORDS[:n_keywords]
    all_projects = []
    service_status = {}

    for service_name, instances in SUPPORTED_SERVICES.items():
        dispatch = SERVICE_DISPATCH.get(service_name)
        if dispatch is None:
            service_status[service_name] = {"status": "unsupported", "instances": {}}
            continue

        svc_status = {"status": "ok", "instances": {}}

        for instance_url in instances:
            inst_projects = []
            inst_ok = True

            # Check online status for Pic4Review before fetching
            if service_name == "Pic4Review":
                if not dry_run:
                    online = check_pic4review_online(instance_url)
                    if not online:
                        svc_status["instances"][instance_url] = "offline"
                        svc_status["status"] = "offline"
                        print(f"[acquisition] Pic4Review instance {instance_url} is OFFLINE")
                        continue
                    else:
                        svc_status["instances"][instance_url] = "online"
                else:
                    svc_status["instances"][instance_url] = "dry-run"

            fetch_fn = dispatch.get("fetch_all")
            
            if dry_run:
                print(f"  [DRY-RUN] {service_name} @ {instance_url} | using fetch_all()")
                continue

            if fetch_fn:
                try:
                    all_raw_projects = fetch_fn(instance_url, bbox)
                    print(f"[acquisition] Fetched {len(all_raw_projects)} total projects from {instance_url}")
                    
                    # Local case-insensitive matching
                    for p in all_raw_projects:
                        matched = []
                        title = p.get("title", "").lower()
                        desc = p.get("description", "").lower()
                        for kw in keywords:
                            if kw.lower() in title or kw.lower() in desc:
                                matched.append(kw)
                        if matched:
                            p["matched_keywords"] = matched
                            inst_projects.append(p)
                    
                    print(f"[acquisition] {len(inst_projects)} projects matched keywords at {instance_url}")
                    
                    # For Tasking Manager projects without bbox, fetch from detail endpoint
                    if service_name == "Tasking Manager":
                        for p in inst_projects:
                            if "bbox" not in p:
                                proj_bbox = fetch_project_bbox_from_detail(instance_url, p["id"])
                                if proj_bbox:
                                    p["bbox"] = proj_bbox
                except Exception as e:
                    print(f"[acquisition] Error fetching all projects for {instance_url}: {e}")
                    inst_ok = False
            else:
                inst_ok = False

            svc_status["instances"][instance_url] = "ok" if inst_ok else "partial"
            all_projects.extend(inst_projects)

        # Determine overall service status
        inst_values = list(svc_status["instances"].values())
        if any(v == "ok" for v in inst_values):
            svc_status["status"] = "ok"
        elif any("online" in str(v) for v in inst_values):
            svc_status["status"] = "online (no search API)"
        elif svc_status["status"] != "offline":
            svc_status["status"] = "error"

        service_status[service_name] = svc_status

    return all_projects, service_status


# ---------------------------------------------------------------------------
# Write results JSON
# ---------------------------------------------------------------------------


def write_results_json(projects, service_status, bbox, output_path):
    """Write the structured results index."""
    results = {
        "node_name": CITY_NAME,
        "generated_at": datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "bbox": list(bbox) if bbox else [],
        "keywords_used": SEARCH_KEYWORDS[:DEFAULT_ACQ_KEYWORDS_COUNT],
        "services_queried": list(SUPPORTED_SERVICES.keys()),
        "service_status": service_status,
        "total_projects_found": len(projects),
        "projects": projects,
    }

    ensure_parent_folder(output_path)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"[acquisition] Results written to {output_path} ({len(projects)} projects)")


# ---------------------------------------------------------------------------
# Generate HTML dashboard
# ---------------------------------------------------------------------------


def generate_dashboard_html(projects, service_status, bbox, output_path):
    """Generate a premium-styled static HTML dashboard with MapLibre v6 map."""

    projects_js = json.dumps(projects, indent=2, ensure_ascii=False)
    status_js = json.dumps(service_status, indent=2, ensure_ascii=False)
    bbox_js = json.dumps(list(bbox) if bbox else [], indent=2, ensure_ascii=False)
    gen_time = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    html = f"""<!--
  Generated automatically by oswm_codebase/datahub/acquisition/generate_acquisition.py
  Do not edit this file directly.
-->
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>OSWM Data Acquisition | {CITY_NAME}</title>
    <meta name="description" content="Pedestrian-data project discovery dashboard for OSWM node: {CITY_NAME}">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&family=Fira+Code:wght@400;500&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://unpkg.com/maplibre-gl@6/dist/maplibre-gl.css" />
    <style>
        :root {{
            --bg-gradient: linear-gradient(135deg, #0f172a 0%, #1e1b4b 100%);
            --card-bg: rgba(30, 41, 59, 0.7);
            --card-border: rgba(255,255,255,0.08);
            --primary: #00f2fe;
            --primary-glow: rgba(0,242,254,0.15);
            --secondary: #4facfe;
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
            --accent-success: #10b981;
            --accent-warning: #f59e0b;
            --accent-error: #ef4444;
            --accent-purple: #8b5cf6;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: 'Outfit', sans-serif;
            background: var(--bg-gradient);
            color: var(--text-main);
            min-height: 100vh;
            line-height: 1.6;
        }}
        body::before {{
            content: '';
            position: fixed;
            top: -20%; left: -10%;
            width: 600px; height: 600px;
            background: radial-gradient(circle, rgba(0,242,254,0.12) 0%, transparent 70%);
            z-index: -1; pointer-events: none;
        }}
        body::after {{
            content: '';
            position: fixed;
            bottom: -10%; right: -10%;
            width: 700px; height: 700px;
            background: radial-gradient(circle, rgba(139,92,246,0.1) 0%, transparent 70%);
            z-index: -1; pointer-events: none;
        }}
        header {{
            background: rgba(15,23,42,0.6);
            backdrop-filter: blur(12px);
            border-bottom: 1px solid var(--card-border);
            padding: 1.25rem 2rem;
        }}
        .header-inner {{
            max-width: 1400px; margin: 0 auto;
            display: flex; justify-content: space-between; align-items: center;
        }}
        .header-inner h1 {{
            font-size: 1.4rem; font-weight: 600;
            background: linear-gradient(to right, var(--primary), var(--secondary));
            -webkit-background-clip: text;
            background-clip: text;
            -webkit-text-fill-color: transparent;
        }}
        .header-inner .timestamp {{
            font-size: 0.85rem; color: var(--text-muted);
            font-family: 'Fira Code', monospace;
        }}
        .container {{
            max-width: 1400px; margin: 2rem auto; padding: 0 2rem;
        }}
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 1.25rem; margin-bottom: 2rem;
        }}
        .stat-card {{
            background: var(--card-bg);
            backdrop-filter: blur(16px);
            border: 1px solid var(--card-border);
            border-radius: 16px;
            padding: 1.5rem;
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
            transition: transform 0.2s, box-shadow 0.2s;
        }}
        .stat-card:hover {{
            transform: translateY(-2px);
            box-shadow: 0 14px 36px rgba(0,0,0,0.3);
        }}
        .stat-card .label {{
            font-size: 0.82rem; text-transform: uppercase;
            letter-spacing: 1px; color: var(--text-muted); margin-bottom: 0.4rem;
        }}
        .stat-card .value {{
            font-size: 2rem; font-weight: 700;
        }}
        .stat-card .value.primary {{ color: var(--primary); }}
        .stat-card .value.purple {{ color: var(--accent-purple); }}
        .stat-card .value.success {{ color: var(--accent-success); }}

        .panel {{
            background: var(--card-bg);
            backdrop-filter: blur(16px);
            border: 1px solid var(--card-border);
            border-radius: 16px;
            padding: 1.5rem;
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
            margin-bottom: 2rem;
        }}
        .panel h2 {{
            font-size: 1.15rem; font-weight: 600; margin-bottom: 1rem;
            display: flex; align-items: center; gap: 0.5rem;
        }}

        /* Service status badges */
        .svc-badges {{
            display: flex; gap: 0.75rem; flex-wrap: wrap; margin-bottom: 1rem;
        }}
        .svc-badge {{
            display: inline-flex; align-items: center; gap: 0.4rem;
            padding: 0.4rem 0.9rem; border-radius: 8px;
            font-size: 0.85rem; font-weight: 500;
            border: 1px solid var(--card-border);
            background: rgba(255,255,255,0.03);
        }}
        .svc-dot {{
            width: 8px; height: 8px; border-radius: 50%;
        }}
        .svc-dot.ok {{ background: var(--accent-success); box-shadow: 0 0 6px var(--accent-success); }}
        .svc-dot.offline {{ background: var(--accent-error); box-shadow: 0 0 6px var(--accent-error); }}
        .svc-dot.error {{ background: var(--accent-warning); box-shadow: 0 0 6px var(--accent-warning); }}

        /* Tabs */
        .tabs {{
            display: flex; gap: 0; margin-bottom: 0;
            border-bottom: 2px solid var(--card-border);
        }}
        .tab-btn {{
            padding: 0.7rem 1.4rem;
            font-family: 'Outfit', sans-serif;
            font-size: 0.9rem; font-weight: 500;
            color: var(--text-muted);
            background: none; border: none; cursor: pointer;
            border-bottom: 2px solid transparent;
            margin-bottom: -2px;
            transition: color 0.2s, border-color 0.2s;
        }}
        .tab-btn:hover {{ color: var(--text-main); }}
        .tab-btn.active {{
            color: var(--primary);
            border-bottom-color: var(--primary);
        }}
        .tab-btn .tab-count {{
            display: inline-block;
            margin-left: 0.4rem;
            padding: 0.05rem 0.4rem;
            border-radius: 10px;
            font-size: 0.72rem; font-weight: 600;
            background: rgba(0,242,254,0.12); color: var(--primary);
        }}

        /* Search + filters */
        .controls {{
            display: flex; gap: 1rem; flex-wrap: wrap; margin-bottom: 1rem;
            margin-top: 1rem;
        }}
        .search-box {{
            flex: 1; min-width: 200px;
            background: rgba(15,23,42,0.5);
            border: 1px solid var(--card-border);
            border-radius: 8px; padding: 0.6rem 1rem;
            color: var(--text-main); font-family: 'Outfit', sans-serif;
            font-size: 0.9rem; outline: none;
            transition: border-color 0.2s;
        }}
        .search-box:focus {{ border-color: rgba(0,242,254,0.4); }}

        /* View Toggle Group */
        .view-btn.active {{
            background: var(--primary) !important;
            color: #0f172a !important;
            box-shadow: 0 2px 8px var(--primary-glow);
        }}

        /* Projects table */
        .projects-table {{
            width: 100%; border-collapse: collapse;
        }}
        .projects-table th {{
            text-align: left; padding: 0.75rem 1rem;
            font-size: 0.78rem; text-transform: uppercase;
            letter-spacing: 0.8px; color: var(--text-muted);
            border-bottom: 1px solid var(--card-border);
            cursor: pointer; user-select: none;
        }}
        .projects-table th:hover {{ color: var(--primary); }}
        .projects-table td {{
            padding: 0.75rem 1rem; font-size: 0.9rem;
            border-bottom: 1px solid rgba(255,255,255,0.03);
            vertical-align: top;
        }}
        .projects-table tr {{
            transition: background 0.15s;
        }}
        .projects-table tr:hover {{
            background: rgba(0,242,254,0.03);
        }}
        .project-title a {{
            color: var(--primary); text-decoration: none; font-weight: 500;
            transition: color 0.2s;
        }}
        .project-title a:hover {{ color: var(--secondary); }}
        .project-desc {{
            font-size: 0.82rem; color: var(--text-muted);
            max-width: 400px; overflow: hidden;
            text-overflow: ellipsis; white-space: nowrap;
        }}
        .kw-tag {{
            display: inline-block;
            padding: 0.1rem 0.45rem; margin: 0.1rem;
            border-radius: 4px; font-size: 0.72rem; font-weight: 600;
            background: rgba(0,242,254,0.1); color: var(--primary);
        }}
        .status-tag {{
            padding: 0.15rem 0.5rem; border-radius: 4px;
            font-size: 0.75rem; font-weight: 600;
        }}
        .status-tag.active {{ background: rgba(16,185,129,0.15); color: var(--accent-success); }}
        .status-tag.other {{ background: rgba(255,255,255,0.08); color: var(--text-muted); }}

        .empty-state {{
            text-align: center; padding: 3rem 1rem;
            color: var(--text-muted);
        }}
        .empty-state .icon {{ font-size: 3rem; margin-bottom: 1rem; }}
        .instance-label {{
            font-size: 0.75rem; color: var(--text-muted);
            font-family: 'Fira Code', monospace;
        }}

        /* Map custom markers */
        .marker-pin {{
            width: 32px;
            height: 32px;
            border-radius: 50% 50% 50% 0;
            position: absolute;
            transform: rotate(-45deg);
            left: 0 !important;
            top: 0 !important;
            margin: 0 !important;
            display: flex;
            align-items: center;
            justify-content: center;
            box-shadow: 0 4px 10px rgba(0,0,0,0.3);
            border: 2px solid #fff;
            cursor: pointer;
            transition: transform 0.2s ease;
        }}
        .marker-pin:hover {{
            transform: rotate(-45deg) scale(1.1);
        }}
        .marker-pin::after {{
            content: '';
            width: 24px;
            height: 24px;
            border-radius: 50%;
            background: rgba(255,255,255,0.2);
            position: absolute;
        }}
        .marker-icon {{
            transform: rotate(45deg);
            font-size: 16px;
            z-index: 2;
            display: flex;
            align-items: center;
            justify-content: center;
        }}
        .marker-tm {{ background: #e04c3f; }}
        .marker-mr {{ background: #10b981; }}
        .marker-p4r {{ background: #8b5cf6; }}

        /* Popup overrides */
        .maplibregl-popup-content {{
            background: #ffffff !important;
            color: #0f172a !important;
            border-radius: 12px !important;
            padding: 12px 16px !important;
            box-shadow: 0 10px 25px rgba(0,0,0,0.2) !important;
            border: 1px solid rgba(0,0,0,0.1) !important;
        }}
        .maplibregl-popup-anchor-top .maplibregl-popup-tip {{ border-bottom-color: #ffffff !important; }}
        .maplibregl-popup-anchor-bottom .maplibregl-popup-tip {{ border-top-color: #ffffff !important; }}
        .maplibregl-popup-anchor-left .maplibregl-popup-tip {{ border-right-color: #ffffff !important; }}
        .maplibregl-popup-anchor-right .maplibregl-popup-tip {{ border-left-color: #ffffff !important; }}
        .maplibregl-popup-close-button {{
            color: #94a3b8 !important;
            font-size: 16px !important;
            padding: 4px 8px !important;
            top: 4px !important;
            right: 4px !important;
        }}

        @media (max-width: 768px) {{
            .container {{ padding: 0 1rem; }}
            .stats-grid {{ grid-template-columns: repeat(2, 1fr); }}
            .projects-table {{ font-size: 0.82rem; }}
            .projects-table td, .projects-table th {{ padding: 0.5rem; }}
            .tabs {{ overflow-x: auto; }}
        }}
    </style>
</head>
<body>
    <header>
        <div class="header-inner">
            <h1>&#x1F6B6; OSWM Data Acquisition &mdash; {CITY_NAME}</h1>
            <span class="timestamp">{gen_time}</span>
        </div>
    </header>

    <div class="container">
        <div class="stats-grid" id="stats-grid"></div>

        <!-- Discovered Projects Panel (First) -->
        <div class="panel">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.25rem; flex-wrap: wrap; gap: 0.75rem;">
                <h2 style="margin-bottom: 0;">&#x1F4CB; Discovered Projects</h2>
                <div class="view-toggle" style="display: flex; background: rgba(15,23,42,0.4); border: 1px solid var(--card-border); border-radius: 8px; padding: 2px;">
                    <button class="view-btn active" id="btn-list-view" onclick="switchView('list')" style="background: none; border: none; padding: 0.4rem 1rem; border-radius: 6px; font-family: 'Outfit', sans-serif; font-size: 0.85rem; font-weight: 500; color: var(--text-muted); cursor: pointer; transition: all 0.2s;">📋 List View</button>
                    <button class="view-btn" id="btn-map-view" onclick="switchView('map')" style="background: none; border: none; padding: 0.4rem 1rem; border-radius: 6px; font-family: 'Outfit', sans-serif; font-size: 0.85rem; font-weight: 500; color: var(--text-muted); cursor: pointer; transition: all 0.2s;">🗺️ Map View</button>
                </div>
            </div>
            
            <div class="tabs" id="service-tabs"></div>
            
            <div class="controls">
                <input class="search-box" id="search" type="text" placeholder="Filter projects by title or keyword&#x2026;">
            </div>
            
            <div id="table-container"></div>
            
            <div id="map-view-container" style="display: none; height: 500px; border-radius: 12px; overflow: hidden; margin-top: 1rem; border: 1px solid var(--card-border); position: relative;">
                <div id="map" style="width: 100%; height: 100%;"></div>
            </div>
        </div>

        <!-- Service Status Panel (Second) -->
        <div class="panel">
            <h2>&#x1F4E1; Service Status</h2>
            <div class="svc-badges" id="svc-badges"></div>
        </div>
    </div>

<script type="module">
import * as maplibregl from 'https://unpkg.com/maplibre-gl@6.0.0/dist/maplibre-gl.mjs';
import {{ Protocol as PmtilesProtocol }} from 'https://cdn.jsdelivr.net/npm/pmtiles@4/+esm';

const pmtilesProtocol = new PmtilesProtocol();
maplibregl.addProtocol('pmtiles', pmtilesProtocol.tile);
const BASEMAP_URL = new URL('../../data/basemaps/light.pmtiles', import.meta.url).href;

const PROJECTS = {projects_js};
const SERVICE_STATUS = {status_js};
const BBOX = {bbox_js};

let activeTab = 'all';
let mapInitialized = false;
let mapObj = null;
let mapMarkers = [];

function init() {{
    renderStats();
    renderServiceBadges();
    renderTabs();
    applyFilters();

    document.getElementById('search').addEventListener('input', applyFilters);
}}

function renderStats() {{
    const grid = document.getElementById('stats-grid');
    const services = new Set(PROJECTS.map(p => p.service));
    const kws = new Set(PROJECTS.flatMap(p => p.matched_keywords || []));

    const cards = [
        {{ label: 'Total Projects', value: PROJECTS.length, cls: 'primary' }},
        {{ label: 'Services Queried', value: Object.keys(SERVICE_STATUS).length, cls: 'purple' }},
        {{ label: 'Unique Keywords', value: kws.size, cls: 'success' }},
        {{ label: 'Active Services', value: services.size, cls: 'primary' }},
    ];

    grid.innerHTML = cards.map(c => `
        <div class="stat-card">
            <div class="label">${{c.label}}</div>
            <div class="value ${{c.cls}}">${{c.value}}</div>
        </div>
    `).join('');
}}

function renderServiceBadges() {{
    const container = document.getElementById('svc-badges');
    container.innerHTML = Object.entries(SERVICE_STATUS).map(([name, info]) => {{
        const status = info.status || 'error';
        let dotCls, label;
        if (status === 'ok') {{ dotCls = 'ok'; label = ''; }}
        else if (status === 'offline') {{ dotCls = 'offline'; label = '(offline server)'; }}
        else if (status.includes('online')) {{ dotCls = 'ok'; label = '(no search API)'; }}
        else {{ dotCls = 'error'; label = `(${{status}})`; }}
        return `<div class="svc-badge"><span class="svc-dot ${{dotCls}}"></span>${{name}} ${{label}}</div>`;
    }}).join('');
}}

function renderTabs() {{
    const tabsEl = document.getElementById('service-tabs');
    const serviceCounts = {{}};
    PROJECTS.forEach(p => {{
        const svc = p.service || 'Unknown';
        serviceCounts[svc] = (serviceCounts[svc] || 0) + 1;
    }});

    let html = `<button class="tab-btn active" data-svc="all" onclick="switchTab('all')">All <span class="tab-count">${{PROJECTS.length}}</span></button>`;
    Object.entries(serviceCounts).forEach(([svc, count]) => {{
        html += `<button class="tab-btn" data-svc="${{svc}}" onclick="switchTab('${{svc}}')">${{svc}} <span class="tab-count">${{count}}</span></button>`;
    }});
    tabsEl.innerHTML = html;
}}

function switchTab(svc) {{
    activeTab = svc;
    document.querySelectorAll('.tab-btn').forEach(btn => {{
        btn.classList.toggle('active', btn.dataset.svc === svc);
    }});
    applyFilters();
}}

function applyFilters() {{
    const q = document.getElementById('search').value.toLowerCase();
    let filtered = PROJECTS;
    if (activeTab !== 'all') filtered = filtered.filter(p => p.service === activeTab);
    if (q) filtered = filtered.filter(p =>
        (p.title || '').toLowerCase().includes(q) ||
        (p.matched_keywords || []).some(k => k.toLowerCase().includes(q)) ||
        (p.description || '').toLowerCase().includes(q)
    );
    renderTable(filtered);
    if (mapInitialized) {{
        updateMapElements(filtered);
    }}
}}

function renderTable(projects) {{
    const c = document.getElementById('table-container');
    if (!projects.length) {{
        c.innerHTML = '<div class="empty-state"><div class="icon">\\uD83D\\uDD0D</div><p>No projects found matching your criteria.</p></div>';
        return;
    }}
    const activeStatuses = new Set(['ready', 'published', 'active', 'building', 'partially loaded']);
    let html = `<table class="projects-table">
        <thead><tr>
            <th>Title</th><th>Instance</th><th>Status</th><th>Keywords</th><th>Description</th>
        </tr></thead><tbody>`;
    projects.forEach(p => {{
        const isActive = activeStatuses.has((p.status || '').toLowerCase());
        const statusCls = isActive ? 'active' : 'other';
        const kws = (p.matched_keywords || []).map(k => `<span class="kw-tag">${{k}}</span>`).join('');
        const instanceHost = (p.instance || '').replace(/^https?:\\/\\//, '').replace(/\\/$/, '');
        html += `<tr>
            <td class="project-title"><a href="${{p.url}}" target="_blank" rel="noopener">${{p.title || 'Untitled'}}</a></td>
            <td><span class="instance-label">${{instanceHost}}</span></td>
            <td><span class="status-tag ${{statusCls}}">${{p.status || 'N/A'}}</span></td>
            <td>${{kws}}</td>
            <td class="project-desc" title="${{(p.description || '').replace(/"/g, '&quot;')}}">${{p.description || ''}}</td>
        </tr>`;
    }});
    html += '</tbody></table>';
    c.innerHTML = html;
}}

function switchView(view) {{
    const listBtn = document.getElementById('btn-list-view');
    const mapBtn = document.getElementById('btn-map-view');
    const tableContainer = document.getElementById('table-container');
    const mapContainer = document.getElementById('map-view-container');
    
    if (view === 'map') {{
        listBtn.classList.remove('active');
        mapBtn.classList.add('active');
        tableContainer.style.display = 'none';
        mapContainer.style.display = 'block';
        
        if (!mapInitialized) {{
            initMap();
        }} else {{
            mapObj.resize();
            applyFilters();
        }}
    }} else {{
        listBtn.classList.add('active');
        mapBtn.classList.remove('active');
        tableContainer.style.display = 'block';
        mapContainer.style.display = 'none';
    }}
}}

function initMap() {{
    mapInitialized = true;
    
    // BBOX format: [south, west, north, east]
    // MapLibre bounds format: [west, south, east, north]
    const bounds = [BBOX[1], BBOX[0], BBOX[3], BBOX[2]];
    
    mapObj = new maplibregl.Map({{
        container: 'map',
        style: {{
            version: 8,
            sources: {{
                'oswm-basemap': {{
                    type: 'raster',
                    url: `pmtiles://${{BASEMAP_URL}}`,
                    tileSize: 256,
                    attribution: 'Basemap © OpenFreeMap, © OpenMapTiles; data © OpenStreetMap contributors'
                }}
            }},
            layers: [{{ id: 'oswm-basemap-tiles', type: 'raster', source: 'oswm-basemap' }}]
        }},
        bounds: bounds,
        fitBoundsOptions: {{ padding: 40 }}
    }});
    
    mapObj.on('load', () => {{
        mapObj.addControl(new maplibregl.NavigationControl());
        
        // Add boundary source and layer
        mapObj.addSource('boundaries', {{
            type: 'geojson',
            data: '../../data/boundaries/polygon.geojson'
        }});
        
        mapObj.addLayer({{
            id: 'boundary-layer',
            type: 'line',
            source: 'boundaries',
            paint: {{
                'line-color': '#00f2fe',
                'line-width': 1.5,
                'line-opacity': 0.6,
                'line-dasharray': [4, 4]
            }}
        }});
        
        mapObj.addSource('project-geometries', {{
            type: 'geojson',
            data: {{ type: 'FeatureCollection', features: [] }}
        }});
        
        mapObj.addLayer({{
            id: 'project-fills',
            type: 'fill',
            source: 'project-geometries',
            paint: {{
                'fill-color': [
                    'match', ['get', 'service'],
                    'Tasking Manager', '#e04c3f',
                    'MapRoulette', '#10b981',
                    'Pic4Review', '#8b5cf6',
                    '#4682b4'
                ],
                'fill-opacity': 0.15
            }}
        }});
        
        mapObj.addLayer({{
            id: 'project-borders',
            type: 'line',
            source: 'project-geometries',
            paint: {{
                'line-color': [
                    'match', ['get', 'service'],
                    'Tasking Manager', '#e04c3f',
                    'MapRoulette', '#10b981',
                    'Pic4Review', '#8b5cf6',
                    '#4682b4'
                ],
                'line-width': 2,
                'line-dasharray': [2, 2]
            }}
        }});
        
        applyFilters();
    }});
}}

function getCentroid(project) {{
    if (project.geometry) {{
        const geom = project.geometry;
        if (geom.type === 'Point') {{
            return geom.coordinates;
        }} else if (geom.type === 'Polygon') {{
            const coords = geom.coordinates[0];
            let sumX = 0, sumY = 0;
            coords.forEach(pt => {{
                sumX += pt[0];
                sumY += pt[1];
            }});
            return [sumX / coords.length, sumY / coords.length];
        }}
    }} else if (project.bbox) {{
        const b = project.bbox;
        return [(b[0] + b[2]) / 2, (b[1] + b[3]) / 2];
    }}
    return null;
}}

function updateMapElements(filteredProjects) {{
    if (!mapObj || !mapObj.getSource('project-geometries')) return;
    
    // Clear existing markers
    mapMarkers.forEach(m => m.remove());
    mapMarkers = [];
    
    const features = [];
    
    filteredProjects.forEach(p => {{
        let geom = null;
        if (p.geometry) {{
            geom = p.geometry;
        }} else if (p.bbox) {{
            // bbox is [west, south, east, north]
            const b = p.bbox;
            geom = {{
                type: 'Polygon',
                coordinates: [[
                    [b[0], b[1]],
                    [b[0], b[3]],
                    [b[2], b[3]],
                    [b[2], b[1]],
                    [b[0], b[1]]
                ]]
            }};
        }}
        
        if (geom) {{
            features.push({{
                type: 'Feature',
                properties: {{ service: p.service, id: p.id, title: p.title }},
                geometry: geom
            }});
        }}
        
        const centroid = getCentroid(p);
        if (centroid) {{
            const el = document.createElement('div');
            el.className = 'marker-pin';
            
            let markerCls = 'marker-tm';
            let iconText = '🗺️';
            if (p.service === 'MapRoulette') {{
                markerCls = 'marker-mr';
                iconText = '🧩';
            }} else if (p.service === 'Pic4Review') {{
                markerCls = 'marker-p4r';
                iconText = '📷';
            }}
            
            el.classList.add(markerCls);
            el.innerHTML = `<span class="marker-icon">${{iconText}}</span>`;
            
            const popupHtml = `
                <div style="color: #0f172a; padding: 0.5rem; font-family: 'Outfit', sans-serif; min-width: 200px;">
                    <h3 style="margin: 0 0 0.25rem 0; font-size: 0.95rem; font-weight: 600; color: #1e293b;">${{p.title || 'Untitled'}}</h3>
                    <div style="font-size: 0.72rem; text-transform: uppercase; font-weight: 700; color: #64748b; margin-bottom: 0.5rem;">
                        ${{p.service}} &bull; ${{p.status || 'N/A'}}
                    </div>
                    <p style="margin: 0 0 0.75rem 0; font-size: 0.8rem; color: #475569; line-height: 1.4; max-height: 100px; overflow-y: auto;">
                        ${{p.description || 'No description available.'}}
                    </p>
                    <a href="${{p.url}}" target="_blank" rel="noopener" style="display: inline-block; background: #00f2fe; color: #0f172a; padding: 0.35rem 0.75rem; border-radius: 6px; font-size: 0.78rem; font-weight: 600; text-decoration: none; box-shadow: 0 2px 6px rgba(0,242,254,0.3); transition: opacity 0.2s;">
                        Open Project
                    </a>
                </div>
            `;
            const popup = new maplibregl.Popup({{ offset: 15 }}).setHTML(popupHtml);
            
            const marker = new maplibregl.Marker({{ element: el, anchor: 'bottom' }})
                .setLngLat(centroid)
                .setPopup(popup)
                .addTo(mapObj);
                
            mapMarkers.push(marker);
        }}
    }});
    
    mapObj.getSource('project-geometries').setData({{
        type: 'FeatureCollection',
        features: features
    }});
}}

init();

window.switchTab = switchTab;
window.switchView = switchView;
</script>
</body>
</html>"""

    ensure_parent_folder(output_path)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[acquisition] Dashboard written to {output_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="OSWM Data Acquisition Runner")
    parser.add_argument("--dry-run", action="store_true", help="Print API URLs without making requests")
    parser.add_argument("--keywords", type=int, default=None, help=f"Number of keywords to use (default: {DEFAULT_ACQ_KEYWORDS_COUNT})")
    args = parser.parse_args()

    n_kw = args.keywords  # None means "use all keywords" in collect_all_projects
    if n_kw is None:
        n_kw_display = len(SEARCH_KEYWORDS)
    else:
        n_kw_display = n_kw
    print(f"[acquisition] Starting acquisition for node: {CITY_NAME}")
    print(f"[acquisition] Using {n_kw_display} keywords: {SEARCH_KEYWORDS[:n_kw_display]}")

    bbox = get_bbox_from_boundary()
    if bbox is None:
        print("[acquisition] ERROR: No bounding box available. Cannot proceed.")
        sys.exit(1)

    print(f"[acquisition] Bounding box: {bbox}")

    # Collect projects
    projects, svc_status = collect_all_projects(bbox, n_keywords=n_kw, dry_run=args.dry_run)

    if args.dry_run:
        print(f"\n[acquisition] DRY-RUN complete. {len(projects)} project URLs would have been queried.")
        return

    # Deduplicate
    projects = deduplicate_results(projects)
    print(f"[acquisition] After deduplication: {len(projects)} unique projects")

    # Post-filter by polygon
    polygon = get_boundary_polygon()
    if polygon:
        pre_count = len(projects)
        projects = filter_by_polygon(projects, polygon)
        print(f"[acquisition] After polygon filter: {len(projects)} (removed {pre_count - len(projects)})")
    # Write outputs
    write_results_json(projects, svc_status, bbox, acquisition_results_path)
    generate_dashboard_html(projects, svc_status, bbox, acquisition_page_path)

    print(f"[acquisition] Done! {len(projects)} projects discovered.")


if __name__ == "__main__":
    main()
