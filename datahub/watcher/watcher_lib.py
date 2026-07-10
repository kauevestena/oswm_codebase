from __future__ import annotations

import os
import sys
from datetime import datetime, timezone, timedelta

# Ensure the parent `datahub` directory is on sys.path so `dh_lib` can be imported
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dh_lib import *  # noqa: F403 – sets up sys.path and folder structure
from functions import read_json  # noqa: F811
from constants import updating_infos_path, boundaries_geojson_path, watcher_page_path, watcher_rss_path, watcher_changesets_rss_path, watcher_history_path, REPO_NAME, USERNAME, node_homepage_url  # noqa: F811
from config import CITY_NAME  # noqa: F811
import requests  # noqa: F811
import geopandas as gpd  # noqa: F811
from functions import dump_json, formatted_datetime_now # noqa: F811

# ---------------------------------------------------------------------------
# OHSOME API
# ---------------------------------------------------------------------------

OHSOME_API_BASE = "https://api.ohsome.org/v1"

# Maps each OSWM data layer to its OHSOME filter expression.
# Filter syntax: https://docs.ohsome.org/ohsome-api/stable/filter.html
OHSOME_FILTER_MAP: dict[str, str] = {
    "sidewalks": "footway=sidewalk and type:way",
    "crossings": "footway=crossing and type:way",
    "kerbs": "(barrier=kerb or kerb=*) and type:node",
    "other_footways": (
        "(highway=footway or highway=steps or highway=living_street"
        " or highway=pedestrian or highway=track or highway=path"
        " or foot=yes or foot=designated or foot=permissive or foot=destination"
        " or footway=alley or footway=path or footway=yes) and type:way"
    ),
}

COMBINED_FILTER = (
    "(footway=sidewalk and type:way) or "
    "(footway=crossing and type:way) or "
    "((barrier=kerb or kerb=*) and type:node) or "
    "((highway=footway or highway=steps or highway=living_street or "
    "highway=pedestrian or highway=track or highway=path or "
    "foot=yes or foot=designated or foot=permissive or foot=destination or "
    "footway=alley or footway=path or footway=yes) and type:way)"
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


_changeset_cache_path = os.path.join(os.path.dirname(watcher_history_path), "changeset_cache.json")

def _load_changeset_cache() -> dict:
    if os.path.exists(_changeset_cache_path):
        try:
            return read_json(_changeset_cache_path)
        except Exception:
            pass
    return {}

def _save_changeset_cache(cache: dict):
    try:
        os.makedirs(os.path.dirname(_changeset_cache_path), exist_ok=True)
        dump_json(cache, _changeset_cache_path)
    except Exception as e:
        print(f"[watcher] Failed to write changeset cache: {e}")

def _fetch_changeset_meta(changeset_id: int) -> dict | None:
    """Fetch changeset metadata from OSM API, using a local JSON cache."""
    cache = _load_changeset_cache()
    cid_str = str(changeset_id)
    if cid_str in cache:
        return cache[cid_str]
    
    url = f"https://api.openstreetmap.org/api/0.6/changeset/{changeset_id}.json"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        cs = data.get("changeset", {})
        
        meta = {
            "id": cs.get("id"),
            "user": cs.get("user", "Unknown"),
            "uid": cs.get("uid"),
            "created_at": cs.get("created_at"),
            "closed_at": cs.get("closed_at"),
            "changes_count": cs.get("changes_count", 0),
            "comment": cs.get("tags", {}).get("comment", ""),
            "created_by": cs.get("tags", {}).get("created_by", ""),
        }
        cache[cid_str] = meta
        _save_changeset_cache(cache)
        return meta
    except Exception as e:
        print(f"[watcher] Failed to fetch changeset {changeset_id} metadata: {e}")
        return None


def _load_last_processed_time(key: str = "Data Fetching") -> datetime | None:
    """Read the last-processed timestamp from *updating_infos_path*."""
    try:
        info = read_json(updating_infos_path)
        raw = info.get(key)
        if raw:
            return datetime.strptime(raw, "%d/%m/%Y %H:%M:%S").replace(
                tzinfo=timezone.utc
            )
    except Exception:
        pass
    return None


def _boundary_bboxes() -> str | None:
    """
    Return the study-area bounding box as an OHSOME *bboxes* parameter string
    (``minlon,minlat,maxlon,maxlat``).
    """
    try:
        gdf = gpd.read_file(boundaries_geojson_path)
        minx, miny, maxx, maxy = gdf.total_bounds
        return f"{minx:.6f},{miny:.6f},{maxx:.6f},{maxy:.6f}"
    except Exception:
        return None


def _parse_iso_timestamp(ts_str: str) -> datetime | None:
    """Parse an ISO-8601 timestamp with varying precision (e.g. ``2026-06-19T10:00Z``)."""
    try:
        val = ts_str.replace("Z", "+00:00")
        if "+" in val:
            dt_part, tz_part = val.split("+")
            if dt_part.count(":") == 1:
                dt_part += ":00"
            val = f"{dt_part}+{tz_part}"
        return datetime.fromisoformat(val)
    except Exception:
        return None


def _ohsome_max_timestamp() -> datetime | None:
    """Fetch the maximum timestamp available in the OHSOME database."""
    try:
        resp = requests.get(f"{OHSOME_API_BASE}/metadata", timeout=10)
        resp.raise_for_status()
        meta = resp.json()
        to_ts = meta.get("extractRegion", {}).get("temporalExtent", {}).get("toTimestamp")
        if to_ts:
            return _parse_iso_timestamp(to_ts)
    except Exception as e:
        print(f"[watcher] Failed to fetch OHSOME metadata: {e}")
    return None


def _ohsome_contributions_count(
    bboxes: str, filter_str: str, since: datetime
) -> int | None:
    """
    Query OHSOME for the number of OSM contributions (additions, modifications,
    deletions) within *bboxes* matching *filter_str* in the interval
    [*since*, now].

    Returns the count (≥ 0) or *None* on error.
    """
    max_ts = _ohsome_max_timestamp()
    now_dt = datetime.now(tz=timezone.utc)

    if max_ts:
        # If the reference timestamp is newer than OHSOME's latest data,
        # OHSOME does not have any newer changes to report.
        if since >= max_ts:
            print(f"[watcher] Last update ({since.isoformat()}) is newer than OHSOME's temporal extent ({max_ts.isoformat()}) — assuming up to date.")
            return 0
        # Restrict the upper bound to the maximum timestamp supported by OHSOME
        end_dt = min(now_dt, max_ts)
    else:
        end_dt = now_dt

    since_iso = since.strftime("%Y-%m-%dT%H:%M:%SZ")
    end_iso = end_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    url = f"{OHSOME_API_BASE}/contributions/count"
    try:
        resp = requests.post(
            url,
            data={
                "bboxes": bboxes,
                "filter": filter_str,
                "time": f"{since_iso}/{end_iso}",
            },
            timeout=60,
        )
        resp.raise_for_status()
        result = resp.json()
        return int(result.get("result", [{}])[0].get("value", 0))
    except Exception as e:
        print(f"[watcher] OHSOME request failed for filter '{filter_str}': {e}")
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def check_layer_needs_update(
    layer: str,
    since: datetime,
    bboxes: str,
) -> bool | None:
    """
    Return *True* if OSM has new contributions for *layer* since *since*,
    *False* if none were found, or *None* if the check could not be performed.
    """
    filter_str = OHSOME_FILTER_MAP.get(layer)
    if filter_str is None:
        print(f"[watcher] No OHSOME filter defined for layer '{layer}'")
        return None

    count = _ohsome_contributions_count(bboxes, filter_str, since)
    if count is None:
        return None
    return count > 0


def needs_update(
    layers: list[str] | None = None,
    since_key: str = "Data Fetching",
) -> dict[str, bool | None]:
    """
    Check whether any of the given *layers* have new OSM contributions since
    the last recorded data-fetch run.

    Parameters
    ----------
    layers :
        Layer names to check.  Defaults to all entries in ``OHSOME_FILTER_MAP``
        (sidewalks, crossings, kerbs, other_footways).
    since_key :
        Key in ``data/updates/registry.json`` used as the reference timestamp.
        Defaults to ``"Data Fetching"``.

    Returns
    -------
    dict mapping each layer name to:
        ``True``  – OSM data changed; update recommended.
        ``False`` – No changes detected; update not needed.
        ``None``  – Check inconclusive (API error or missing timestamp).
    """
    if layers is None:
        layers = list(OHSOME_FILTER_MAP.keys())

    since = _load_last_processed_time(since_key)
    if since is None:
        print(
            f"[watcher] No '{since_key}' timestamp in updates registry"
            " — assuming update is needed."
        )
        return {layer: True for layer in layers}

    bboxes = _boundary_bboxes()
    if bboxes is None:
        print("[watcher] Could not read boundary geometry — cannot check for updates.")
        return {layer: None for layer in layers}

    print(f"[watcher] Checking for OSM changes since {since.isoformat()} ...")
    return {layer: check_layer_needs_update(layer, since, bboxes) for layer in layers}


def any_layer_needs_update(**kwargs) -> bool:
    """
    Return *True* if *any* layer needs updating (or if any check was
    inconclusive — conservative).  Return *False* only when all layers are
    confirmed up-to-date.
    """
    results = needs_update(**kwargs)
    return any(v is not False for v in results.values())

# ---------------------------------------------------------------------------
# RSS and Dashboard Publishing
# ---------------------------------------------------------------------------

def get_changeset_activity(bboxes: str, end_dt: datetime) -> dict:
    """
    Fetch changeset activity for:
    - Yesterday: end_dt - 1 day to end_dt (all contribution types)
    - 120 Days deletions: end_dt - 120 days to end_dt (deletions only)
    """
    # 1. Yesterday's changesets
    yesterday_start = end_dt - timedelta(days=1)
    time_yesterday = f"{yesterday_start.strftime('%Y-%m-%dT%H:%M:%SZ')},{end_dt.strftime('%Y-%m-%dT%H:%M:%SZ')}"
    
    print(f"[watcher] Fetching yesterday's changesets ({yesterday_start.strftime('%Y-%m-%d')} to {end_dt.strftime('%Y-%m-%d')}) ...")
    yesterday_changesets = []
    
    try:
        resp = requests.post(
            f"{OHSOME_API_BASE}/contributions/geometry",
            data={
                "bboxes": bboxes,
                "filter": COMBINED_FILTER,
                "time": time_yesterday,
                "properties": "metadata",
            },
            timeout=90,
        )
        resp.raise_for_status()
        features = resp.json().get("features", [])
        
        # Group by changeset ID
        by_cs = {}
        for f in features:
            props = f.get("properties", {})
            cs_id = props.get("@contributionChangesetId")
            if not cs_id:
                continue
            if cs_id not in by_cs:
                by_cs[cs_id] = {"additions": 0, "modifications": 0, "deletions": 0, "timestamp": props.get("@timestamp")}
            
            if props.get("@creation"):
                by_cs[cs_id]["additions"] += 1
            elif props.get("@deletion"):
                by_cs[cs_id]["deletions"] += 1
            elif props.get("@tagChange") or props.get("@geometryChange"):
                by_cs[cs_id]["modifications"] += 1
                
        for cs_id, counts in by_cs.items():
            meta = _fetch_changeset_meta(cs_id)
            if meta:
                yesterday_changesets.append({
                    "id": cs_id,
                    "user": meta["user"],
                    "uid": meta["uid"],
                    "comment": meta["comment"],
                    "created_at": meta["created_at"],
                    "changes_count": meta["changes_count"],
                    "additions": counts["additions"],
                    "modifications": counts["modifications"],
                    "deletions": counts["deletions"],
                })
        
        # Sort by total contributions
        yesterday_changesets.sort(key=lambda x: (x["additions"] + x["modifications"] + x["deletions"]), reverse=True)
    except Exception as e:
        print(f"[watcher] Failed to fetch yesterday's changesets: {e}")
        
    # 2. 120 Days Deletions Changesets
    start_120 = end_dt - timedelta(days=120)
    time_120 = f"{start_120.strftime('%Y-%m-%dT%H:%M:%SZ')},{end_dt.strftime('%Y-%m-%dT%H:%M:%SZ')}"
    print(f"[watcher] Fetching 120 days deletions changesets ({start_120.strftime('%Y-%m-%d')} to {end_dt.strftime('%Y-%m-%d')}) ...")
    
    top_deletions = []
    try:
        resp = requests.post(
            f"{OHSOME_API_BASE}/contributions/geometry",
            data={
                "bboxes": bboxes,
                "filter": COMBINED_FILTER,
                "time": time_120,
                "properties": "metadata",
            },
            timeout=120,
        )
        resp.raise_for_status()
        features = resp.json().get("features", [])
        
        by_cs_del = {}
        for f in features:
            props = f.get("properties", {})
            if not props.get("@deletion"):
                continue
            cs_id = props.get("@contributionChangesetId")
            if not cs_id:
                continue
            if cs_id not in by_cs_del:
                by_cs_del[cs_id] = 0
            by_cs_del[cs_id] += 1
            
        sorted_dels = sorted(by_cs_del.items(), key=lambda x: x[1], reverse=True)[:5]
        
        for cs_id, del_count in sorted_dels:
            meta = _fetch_changeset_meta(cs_id)
            if meta:
                top_deletions.append({
                    "id": cs_id,
                    "user": meta["user"],
                    "uid": meta["uid"],
                    "comment": meta["comment"],
                    "created_at": meta["created_at"],
                    "changes_count": meta["changes_count"],
                    "deletions": del_count,
                })
    except Exception as e:
        print(f"[watcher] Failed to fetch 120 days deletion changesets: {e}")
        
    return {
        "yesterday": yesterday_changesets,
        "top_deletions": top_deletions
    }


def fetch_daily_contributions(layer: str, bboxes: str, start_dt: datetime, end_dt: datetime) -> list[dict]:
    filter_str = OHSOME_FILTER_MAP.get(layer)
    start_iso = start_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    end_iso = end_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    
    url = f"{OHSOME_API_BASE}/contributions/count"
    
    def _fetch(ctype):
        try:
            resp = requests.post(
                url,
                data={
                    "bboxes": bboxes,
                    "filter": filter_str,
                    "time": f"{start_iso}/{end_iso}/P1D",
                    "contributionType": ctype
                },
                timeout=60,
            )
            resp.raise_for_status()
            return resp.json().get("result", [])
        except Exception as e:
            print(f"[watcher] OHSOME daily request failed for filter '{filter_str}', type '{ctype}': {e}")
            return []

    res_add = _fetch("creation")
    res_mod = _fetch("tagChange,geometryChange")
    res_del = _fetch("deletion")
    
    daily_dict = {}
    
    for r in res_add:
        dt = _parse_iso_timestamp(r["fromTimestamp"]).strftime("%Y-%m-%d")
        if dt not in daily_dict: daily_dict[dt] = {"additions": 0, "modifications": 0, "deletions": 0}
        daily_dict[dt]["additions"] += int(float(r.get("value", 0)))
        
    for r in res_mod:
        dt = _parse_iso_timestamp(r["fromTimestamp"]).strftime("%Y-%m-%d")
        if dt not in daily_dict: daily_dict[dt] = {"additions": 0, "modifications": 0, "deletions": 0}
        daily_dict[dt]["modifications"] += int(float(r.get("value", 0)))
        
    for r in res_del:
        dt = _parse_iso_timestamp(r["fromTimestamp"]).strftime("%Y-%m-%d")
        if dt not in daily_dict: daily_dict[dt] = {"additions": 0, "modifications": 0, "deletions": 0}
        daily_dict[dt]["deletions"] += int(float(r.get("value", 0)))
        
    daily_counts = []
    for dt, counts in daily_dict.items():
        total = counts["additions"] + counts["modifications"] + counts["deletions"]
        daily_counts.append({
            "date": dt,
            "count": total,
            "additions": counts["additions"],
            "modifications": counts["modifications"],
            "deletions": counts["deletions"]
        })
        
    return daily_counts

def update_watcher_history(layers: list[str], bboxes: str) -> dict:
    history_path = watcher_history_path
    
    try:
        history = read_json(history_path)
    except Exception:
        history = {"layers": {}}
        
    now_dt = datetime.now(tz=timezone.utc)
    max_ts = _ohsome_max_timestamp()
    if max_ts:
        end_dt = min(now_dt, max_ts)
    else:
        end_dt = now_dt
        
    end_dt = end_dt.replace(hour=0, minute=0, second=0, microsecond=0)
    
    for layer in layers:
        if layer not in history["layers"]:
            history["layers"][layer] = []
            
        layer_history = history["layers"][layer]
        
        if layer_history:
            latest_date_str = max([item["date"] for item in layer_history])
            start_dt = datetime.strptime(latest_date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        else:
            start_dt = end_dt - timedelta(days=120)
            
        if start_dt < end_dt:
            print(f"[watcher] Fetching daily counts for {layer} from {start_dt.strftime('%Y-%m-%d')} to {end_dt.strftime('%Y-%m-%d')} ...")
            new_counts = fetch_daily_contributions(layer, bboxes, start_dt, end_dt)
            
            existing_dates = {item["date"]: item for item in layer_history}
            for nc in new_counts:
                existing_dates[nc["date"]] = nc
            
            sorted_dates = sorted(existing_dates.keys())
            layer_history = [existing_dates[d] for d in sorted_dates[-120:]]
            history["layers"][layer] = layer_history
            
    history["last_updated"] = formatted_datetime_now()
    dump_json(history, history_path)
    return history

def generate_rss_feed(history: dict):
    from email.utils import formatdate
    
    pub_date = formatdate(timeval=None, localtime=False, usegmt=True)
    rss = f"""<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0">
<channel>
    <title>OSWM Watcher Updates - {CITY_NAME}</title>
    <link>{node_homepage_url}</link>
    <description>Daily OSM contribution counts for OpenSidewalkMap layers in {CITY_NAME}.</description>
    <lastBuildDate>{pub_date}</lastBuildDate>
"""
    
    # We will generate one item per day that had > 0 contributions across any layer
    # First, pivot data by date
    dates = set()
    for layer, items in history.get("layers", {}).items():
        for item in items:
            dates.add(item["date"])
            
    for date_str in sorted(list(dates), reverse=True):
        total_for_day = 0
        tot_adds = 0
        tot_mods = 0
        tot_dels = 0
        desc_lines = []
        for layer, items in history.get("layers", {}).items():
            item_for_day = next((i for i in items if i["date"] == date_str), None)
            if item_for_day and item_for_day.get("count", 0) > 0:
                count = item_for_day["count"]
                adds = item_for_day.get("additions", 0)
                mods = item_for_day.get("modifications", 0)
                dels = item_for_day.get("deletions", 0)
                
                total_for_day += count
                tot_adds += adds
                tot_mods += mods
                tot_dels += dels
                
                desc_lines.append(f"&lt;li&gt;{layer}: {count} contributions ({adds} additions, {mods} modifications, {dels} deletions)&lt;/li&gt;")
                
        if total_for_day > 0:
            item_date = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            item_pub_date = formatdate(timeval=item_date.timestamp(), localtime=False, usegmt=True)
            desc_html = f"&lt;p&gt;&lt;strong&gt;Total for {date_str}: {total_for_day} contributions ({tot_adds} additions, {tot_mods} modifications, {tot_dels} deletions)&lt;/strong&gt;&lt;/p&gt;&lt;ul&gt;{''.join(desc_lines)}&lt;/ul&gt;"
            rss += f"""    <item>
        <title>Updates on {date_str}</title>
        <link>{node_homepage_url}hub/watcher/index.html</link>
        <description>{desc_html}</description>
        <pubDate>{item_pub_date}</pubDate>
        <guid isPermaLink="false">{date_str}</guid>
    </item>
"""

    rss += """</channel>
</rss>"""
    
    with open(watcher_rss_path, "w", encoding="utf-8") as f:
        f.write(rss)

def generate_changeset_rss_feed(activity: dict):
    from email.utils import formatdate
    import html
    
    pub_date = formatdate(timeval=None, localtime=False, usegmt=True)
    rss = f"""<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0">
<channel>
    <title>OSWM Watcher Changeset Activity - {CITY_NAME}</title>
    <link>{node_homepage_url}hub/watcher/index.html</link>
    <description>OSM changeset activity monitoring and deletion watch for OpenSidewalkMap interest features in {CITY_NAME}.</description>
    <lastBuildDate>{pub_date}</lastBuildDate>
"""

    # Add yesterday's changesets
    for cs in activity.get("yesterday", []):
        cs_id = cs["id"]
        user = cs["user"]
        adds = cs["additions"]
        mods = cs["modifications"]
        dels = cs["deletions"]
        comment = html.escape(cs.get("comment", ""))
        
        # Link to OSM changeset page
        link = f"https://www.openstreetmap.org/changeset/{cs_id}"
        osmcha_link = f"https://osmcha.org/changesets/{cs_id}"
        user_link = f"https://www.openstreetmap.org/user/{html.escape(user)}"
        
        title = f"[Activity] OSM Changeset {cs_id} by {html.escape(user)} ({adds} additions, {mods} modifications, {dels} deletions)"
        
        desc_html = f"""<p><strong>OSM Changeset {cs_id}</strong> by <a href="{user_link}">{html.escape(user)}</a></p>
<p><strong>Comment:</strong> {comment}</p>
<p><strong>Edits to OSWM features:</strong></p>
<ul>
    <li>Additions (creations): {adds}</li>
    <li>Modifications (tags/geom): {mods}</li>
    <li>Deletions: {dels}</li>
</ul>
<p><strong>Links:</strong> <a href="{link}">OSM</a> | <a href="{osmcha_link}">OSMCha</a></p>
"""
        desc_escaped = html.escape(desc_html)
        
        item_pub_date = pub_date
        if cs.get("created_at"):
            try:
                dt = datetime.strptime(cs["created_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                item_pub_date = formatdate(timeval=dt.timestamp(), localtime=False, usegmt=True)
            except Exception:
                pass
                
        rss += f"""    <item>
        <title>{title}</title>
        <link>{link}</link>
        <description>{desc_escaped}</description>
        <pubDate>{item_pub_date}</pubDate>
        <guid isPermaLink="false">activity_{cs_id}</guid>
    </item>
"""

    # Add top 5 deletion changesets (if they have deletions > 0)
    for cs in activity.get("top_deletions", []):
        cs_id = cs["id"]
        user = cs["user"]
        dels = cs["deletions"]
        comment = html.escape(cs.get("comment", ""))
        
        link = f"https://www.openstreetmap.org/changeset/{cs_id}"
        osmcha_link = f"https://osmcha.org/changesets/{cs_id}"
        user_link = f"https://www.openstreetmap.org/user/{html.escape(user)}"
        
        title = f"[Alert] High Deletion OSM Changeset {cs_id} by {html.escape(user)} ({dels} deletions)"
        
        desc_html = f"""<p><strong>High Deletion Alert for OSM Changeset {cs_id}</strong> by <a href="{user_link}">{html.escape(user)}</a></p>
<p><strong>Comment:</strong> {comment}</p>
<p><strong>Deletions to OSWM features:</strong> {dels}</p>
<p><strong>Links:</strong> <a href="{link}">OSM</a> | <a href="{osmcha_link}">OSMCha</a></p>
"""
        desc_escaped = html.escape(desc_html)
        
        item_pub_date = pub_date
        if cs.get("created_at"):
            try:
                dt = datetime.strptime(cs["created_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                item_pub_date = formatdate(timeval=dt.timestamp(), localtime=False, usegmt=True)
            except Exception:
                pass
                
        rss += f"""    <item>
        <title>{title}</title>
        <link>{link}</link>
        <description>{desc_escaped}</description>
        <pubDate>{item_pub_date}</pubDate>
        <guid isPermaLink="false">deletion_alert_{cs_id}</guid>
    </item>
"""

    rss += """</channel>
</rss>"""
    
    with open(watcher_changesets_rss_path, "w", encoding="utf-8") as f:
        f.write(rss)

def generate_watcher_page(history: dict, results: dict, activity: dict):
    # Prepare data for the stacked bar chart
    layers = list(history.get("layers", {}).keys())
    
    # Find all unique dates across all layers
    dates = set()
    for layer in layers:
        for item in history["layers"][layer]:
            dates.add(item["date"])
    dates = sorted(list(dates))
    
    # We will build chartData for Total and for each layer
    chart_data_dict = {"Total": []}
    for layer in layers:
        chart_data_dict[layer] = []
        
    for d in dates:
        # Total
        add_tot = sum(next((i.get('additions', 0) for i in history["layers"][layer] if i["date"] == d), 0) for layer in layers)
        mod_tot = sum(next((i.get('modifications', 0) for i in history["layers"][layer] if i["date"] == d), 0) for layer in layers)
        del_tot = sum(next((i.get('deletions', 0) for i in history["layers"][layer] if i["date"] == d), 0) for layer in layers)
        chart_data_dict["Total"].append(f"{{ date: '{d}', 'Additions': {add_tot}, 'Modifications': {mod_tot}, 'Deletions': {del_tot} }}")
        
        # Individual Layers
        for layer in layers:
            item = next((i for i in history["layers"][layer] if i["date"] == d), {})
            add_l = item.get('additions', 0)
            mod_l = item.get('modifications', 0)
            del_l = item.get('deletions', 0)
            chart_data_dict[layer].append(f"{{ date: '{d}', 'Additions': {add_l}, 'Modifications': {mod_l}, 'Deletions': {del_l} }}")
            
    chart_data_js = "const chartData = {\n"
    for key, data_list in chart_data_dict.items():
        chart_data_js += f"  '{key}': [" + ",".join(data_list) + "],\n"
    chart_data_js += "};"

    # Yesterday's Changesets HTML
    yesterday_html = ""
    yesterday_list = activity.get("yesterday", [])
    if not yesterday_list:
        yesterday_html = "<p style='color: var(--text-muted); padding: 0.5rem 0;'>No changesets affecting OSWM features yesterday.</p>"
    else:
        yesterday_html = """
        <div style="overflow-x: auto;">
            <table>
                <thead>
                    <tr>
                        <th>Changeset ID</th>
                        <th>User</th>
                        <th>Comment</th>
                        <th>Changes</th>
                        <th>Edits (Add/Mod/Del)</th>
                        <th>Links</th>
                    </tr>
                </thead>
                <tbody>
        """
        for cs in yesterday_list:
            import html as pyhtml
            comment = pyhtml.escape(cs.get("comment", ""))
            user = pyhtml.escape(cs["user"])
            yesterday_html += f"""
                <tr>
                    <td><code>{cs["id"]}</code></td>
                    <td><a href="https://www.openstreetmap.org/user/{user}" target="_blank" style="color: var(--text-main); text-decoration: none; font-weight: 500;">{user}</a></td>
                    <td><div class="comment-text" title="{comment}">{comment}</div></td>
                    <td>{cs["changes_count"]}</td>
                    <td>
                        <span class="badge badge-add">+{cs["additions"]}</span>
                        <span class="badge badge-mod">~{cs["modifications"]}</span>
                        <span class="badge badge-del">-{cs["deletions"]}</span>
                    </td>
                    <td>
                        <div class="link-group">
                            <a href="https://www.openstreetmap.org/changeset/{cs["id"]}" target="_blank">OSM</a>
                            <a href="https://osmcha.org/changesets/{cs["id"]}" target="_blank">OSMCha</a>
                        </div>
                    </td>
                </tr>
            """
        yesterday_html += "</tbody></table></div>"

    # Top 5 Deletions HTML
    deletions_html = ""
    deletions_list = activity.get("top_deletions", [])
    if not deletions_list:
        deletions_html = "<p style='color: var(--text-muted); padding: 0.5rem 0;'>No deletion changesets in the last 120 days.</p>"
    else:
        deletions_html = """
        <div style="overflow-x: auto;">
            <table>
                <thead>
                    <tr>
                        <th>Changeset ID</th>
                        <th>User</th>
                        <th>Comment</th>
                        <th>Date</th>
                        <th>Changes</th>
                        <th>OSWM Deletions</th>
                        <th>Links</th>
                    </tr>
                </thead>
                <tbody>
        """
        for cs in deletions_list:
            import html as pyhtml
            comment = pyhtml.escape(cs.get("comment", ""))
            user = pyhtml.escape(cs["user"])
            date_str = cs.get("created_at", "")[:10]
            deletions_html += f"""
                <tr>
                    <td><code>{cs["id"]}</code></td>
                    <td><a href="https://www.openstreetmap.org/user/{user}" target="_blank" style="color: var(--text-main); text-decoration: none; font-weight: 500;">{user}</a></td>
                    <td><div class="comment-text" title="{comment}">{comment}</div></td>
                    <td>{date_str}</td>
                    <td>{cs["changes_count"]}</td>
                    <td><span class="badge badge-del" style="font-size: 0.85rem; padding: 0.3rem 0.6rem;">-{cs["deletions"]} deletions</span></td>
                    <td>
                        <div class="link-group">
                            <a href="https://www.openstreetmap.org/changeset/{cs["id"]}" target="_blank">OSM</a>
                            <a href="https://osmcha.org/changesets/{cs["id"]}" target="_blank">OSMCha</a>
                        </div>
                    </td>
                </tr>
            """
        deletions_html += "</tbody></table></div>"

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>OSWM Watcher Dashboard | {CITY_NAME}</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&family=Fira+Code:wght@400;500&display=swap" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js"></script>
    <style>
        :root {{
            --bg-gradient: linear-gradient(135deg, #0f172a 0%, #1e1b4b 100%);
            --card-bg: rgba(30, 41, 59, 0.7);
            --card-border: rgba(255, 255, 255, 0.08);
            --primary: #00f2fe;
            --secondary: #4facfe;
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: 'Outfit', sans-serif;
            background: var(--bg-gradient);
            color: var(--text-main);
            min-height: 100vh;
        }}
        header {{
            background: rgba(15, 23, 42, 0.6);
            backdrop-filter: blur(12px);
            border-bottom: 1px solid var(--card-border);
            padding: 1.25rem 2rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        header h1 {{
            font-size: 1.35rem;
            font-weight: 600;
            background: linear-gradient(to right, var(--primary), var(--secondary));
            -webkit-background-clip: text;
            background-clip: text;
            -webkit-text-fill-color: transparent;
        }}
        .btn {{
            padding: 0.5rem 1.15rem;
            border-radius: 8px;
            font-weight: 500;
            text-decoration: none;
            background: rgba(255, 255, 255, 0.05);
            color: var(--text-main);
            border: 1px solid var(--card-border);
            transition: all 0.2s ease;
        }}
        .btn:hover {{ background: rgba(255, 255, 255, 0.1); }}
        .btn-primary {{
            background: linear-gradient(135deg, var(--primary) 0%, var(--secondary) 100%);
            color: #0f172a;
            border: none;
        }}
        .container {{
            max-width: 1200px;
            margin: 2rem auto;
            padding: 0 2rem;
        }}
        .glass-panel {{
            background: var(--card-bg);
            backdrop-filter: blur(16px);
            border: 1px solid var(--card-border);
            border-radius: 16px;
            padding: 1.5rem;
            margin-bottom: 2rem;
        }}
        .status-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 1rem;
            margin-top: 1.5rem;
        }}
        .status-card {{
            background: rgba(15, 23, 42, 0.5);
            border: 1px solid var(--card-border);
            border-radius: 8px;
            padding: 1rem;
            text-align: center;
        }}
        .status-card h3 {{ font-size: 1rem; margin-bottom: 0.5rem; color: var(--text-muted); }}
        .status-card .status-value {{ font-size: 1.25rem; font-weight: 600; }}
        .status-true {{ color: #f87171; }} /* Needs update -> Red */
        .status-false {{ color: #34d399; }} /* Up to date -> Green */
        .status-none {{ color: #fbbf24; }} /* Unknown -> Yellow */
        
        .tabs {{
            display: flex;
            gap: 0.5rem;
            margin-bottom: 1rem;
            border-bottom: 1px solid var(--card-border);
            padding-bottom: 1rem;
            overflow-x: auto;
        }}
        .tab-btn {{
            background: transparent;
            border: 1px solid var(--card-border);
            color: var(--text-muted);
            padding: 0.5rem 1rem;
            border-radius: 8px;
            cursor: pointer;
            font-family: inherit;
            font-size: 0.95rem;
            transition: all 0.2s ease;
            white-space: nowrap;
        }}
        .tab-btn:hover {{
            color: var(--text-main);
            background: rgba(255, 255, 255, 0.05);
        }}
        .tab-btn.active {{
            background: rgba(255, 255, 255, 0.1);
            color: var(--text-main);
            border-color: var(--secondary);
        }}
        
        #chart-container {{
            width: 100%;
            height: 400px;
            margin-top: 1rem;
        }}
        .header-actions {{ display: flex; gap: 1rem; }}

        /* Collapsible Changeset Panels & Tables styling */
        .collapsible-header {{
            background: rgba(15, 23, 42, 0.4);
            border: 1px solid var(--card-border);
            border-radius: 8px;
            padding: 1rem;
            margin-top: 1rem;
            cursor: pointer;
            outline: none;
            user-select: none;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .collapsible-header::-webkit-details-marker {{
            display: none;
        }}
        .collapsible-header::after {{
            content: '▼';
            font-size: 0.8rem;
            color: var(--text-muted);
            transition: transform 0.2s ease;
        }}
        details[open] .collapsible-header::after {{
            transform: rotate(180deg);
        }}
        .collapsible-content {{
            padding: 1rem;
            border: 1px solid var(--card-border);
            border-top: none;
            border-bottom-left-radius: 8px;
            border-bottom-right-radius: 8px;
            background: rgba(15, 23, 42, 0.2);
            margin-bottom: 1rem;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 1rem;
            font-size: 0.95rem;
        }}
        th, td {{
            text-align: left;
            padding: 0.75rem 1rem;
            border-bottom: 1px solid var(--card-border);
        }}
        th {{
            font-weight: 500;
            color: var(--text-muted);
        }}
        tr:hover {{
            background: rgba(255, 255, 255, 0.02);
        }}
        .link-group {{
            display: flex;
            gap: 0.5rem;
        }}
        .link-group a {{
            color: var(--primary);
            text-decoration: none;
            font-weight: 500;
        }}
        .link-group a:hover {{
            text-decoration: underline;
        }}
        .badge {{
            padding: 0.25rem 0.5rem;
            border-radius: 4px;
            font-size: 0.8rem;
            font-weight: 500;
        }}
        .badge-add {{ background: rgba(16, 185, 129, 0.2); color: #10b981; }}
        .badge-mod {{ background: rgba(245, 158, 11, 0.2); color: #f59e0b; }}
        .badge-del {{ background: rgba(239, 68, 68, 0.2); color: #ef4444; }}
        .comment-text {{
            max-width: 300px;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            color: var(--text-muted);
        }}
        .comment-text:hover {{
            white-space: normal;
            word-break: break-all;
        }}
    </style>
</head>
<body>
    <header>
        <h1>OSWM Watcher Dashboard | {CITY_NAME}</h1>
        <div class="header-actions">
            <a href="../../index.html" class="btn">Node Home</a>
            <a href="feed.xml" class="btn btn-primary">Daily RSS</a>
            <a href="changesets.xml" class="btn btn-primary">Changeset RSS</a>
        </div>
    </header>
    <div class="container">
        <div class="glass-panel">
            <h2>Current Status</h2>
            <p style="color: var(--text-muted); margin-top: 0.5rem;">Last Checked: {history.get('last_updated', 'Unknown')}</p>
            <div class="status-grid">
    """
    
    for layer, status in results.items():
        if status is True:
            label = "UPDATE NEEDED"
            css_class = "status-true"
        elif status is False:
            label = "Up to date"
            css_class = "status-false"
        else:
            label = "UNKNOWN"
            css_class = "status-none"
            
        html_content += f"""                <div class="status-card">
                    <h3>{layer}</h3>
                    <div class="status-value {css_class}">{label}</div>
                </div>
"""

    html_content += f"""            </div>
        </div>

        <div class="glass-panel">
            <h2>Daily Contributions (Last 120 Days)</h2>
            <div class="tabs" id="chart-tabs">
                <button class="tab-btn active" onclick="updateChart('Total', this)">Total</button>
"""
    for layer in layers:
        html_content += f"""                <button class="tab-btn" onclick="updateChart('{layer}', this)">{layer}</button>
"""
    html_content += f"""            </div>
            <div id="chart-container"></div>
        </div>

        <div class="glass-panel">
            <h2>Changeset Activity & Vandalism Watch</h2>
            <p style="color: var(--text-muted); margin-top: 0.5rem; margin-bottom: 1.5rem;">
                Monitor individual OSM changesets touching OSWM interest features to identify potential vandalism.
            </p>
            
            <details>
                <summary class="collapsible-header">
                    <span style="font-weight: 500; font-size: 1.1rem;">Yesterday's Changesets</span>
                </summary>
                <div class="collapsible-content">
                    {yesterday_html}
                </div>
            </details>
            
            <div style="margin-top: 2rem;">
                <h3 style="font-weight: 500; font-size: 1.1rem; margin-bottom: 1rem;">Top 5 Deletions (Last 120 Days)</h3>
                {deletions_html}
            </div>
        </div>
    </div>

    <script>
        {chart_data_js}
        
        const chartDom = document.getElementById('chart-container');
        const myChart = echarts.init(chartDom, 'dark', {{ renderer: 'svg' }});
        
        function updateChart(tabName, btnElement) {{
            // Update active class
            if (btnElement) {{
                document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
                btnElement.classList.add('active');
            }}
            
            const data = chartData[tabName];
            
            const option = {{
                backgroundColor: 'transparent',
                tooltip: {{ trigger: 'axis', axisPointer: {{ type: 'shadow' }} }},
                legend: {{ data: ['Additions', 'Modifications', 'Deletions'], textStyle: {{ color: '#94a3b8' }} }},
                grid: {{ left: '3%', right: '4%', bottom: '3%', containLabel: true }},
                xAxis: [{{ type: 'category', data: data.map(item => item.date) }}],
                yAxis: [{{ type: 'value' }}],
                series: [
                    {{
                        name: 'Additions',
                        type: 'bar',
                        stack: 'total',
                        itemStyle: {{ color: '#10b981' }},
                        emphasis: {{ focus: 'series' }},
                        data: data.map(item => item['Additions'])
                    }},
                    {{
                        name: 'Modifications',
                        type: 'bar',
                        stack: 'total',
                        itemStyle: {{ color: '#f59e0b' }},
                        emphasis: {{ focus: 'series' }},
                        data: data.map(item => item['Modifications'])
                    }},
                    {{
                        name: 'Deletions',
                        type: 'bar',
                        stack: 'total',
                        itemStyle: {{ color: '#ef4444' }},
                        emphasis: {{ focus: 'series' }},
                        data: data.map(item => item['Deletions'])
                    }}
                ]
            }};
            myChart.setOption(option);
        }}
        
        // Initial render
        updateChart('Total', document.querySelector('.tab-btn.active'));
        
        window.addEventListener('resize', function() {{
            myChart.resize();
        }});
    </script>
</body>
</html>"""
    
    with open(watcher_page_path, "w", encoding="utf-8") as f:
        f.write(html_content)



# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    results = needs_update()

    print("\n--- Watcher results ---")
    any_update = False
    for layer, status in results.items():
        if status is True:
            label = "UPDATE NEEDED"
            any_update = True
        elif status is False:
            label = "up to date"
        else:
            label = "UNKNOWN (check failed)"
            any_update = True  # conservative

        print(f"  {layer:<20} {label}")

    print()
    if any_update:
        print("Conclusion: at least one layer has changes — run the full pipeline.")
    else:
        print("Conclusion: no changes detected — skipping data download.")
        
    bboxes = _boundary_bboxes()
    if bboxes:
        print("\n--- Updating History and Generating Dashboard ---")
        history = update_watcher_history(list(results.keys()), bboxes)
        
        # Calculate end_dt for changeset queries
        now_dt = datetime.now(tz=timezone.utc)
        max_ts = _ohsome_max_timestamp()
        end_dt = min(now_dt, max_ts) if max_ts else now_dt
        end_dt = end_dt.replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Fetch changeset activity
        activity = get_changeset_activity(bboxes, end_dt)
        
        generate_rss_feed(history)
        generate_changeset_rss_feed(activity)
        generate_watcher_page(history, results, activity)
        print("Done! Dashboard generated at:", watcher_page_path)
    
    if any_update:
        sys.exit(1)
    else:
        sys.exit(0)
