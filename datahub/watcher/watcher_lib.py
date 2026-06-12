from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

# Ensure the parent `datahub` directory is on sys.path so `dh_lib` can be imported
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dh_lib import *  # provides: requests, gpd, read_json, updating_infos_path, boundaries_geojson_path, ...

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


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


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


def _ohsome_contributions_count(
    bboxes: str, filter_str: str, since: datetime
) -> int | None:
    """
    Query OHSOME for the number of OSM contributions (additions, modifications,
    deletions) within *bboxes* matching *filter_str* in the interval
    [*since*, now].

    Returns the count (≥ 0) or *None* on error.
    """
    now_iso = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    since_iso = since.strftime("%Y-%m-%dT%H:%M:%SZ")
    url = f"{OHSOME_API_BASE}/contributions/count"
    try:
        resp = requests.post(
            url,
            data={
                "bboxes": bboxes,
                "filter": filter_str,
                "time": f"{since_iso}/{now_iso}",
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
        Key in ``data/last_updated.json`` used as the reference timestamp.
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
            f"[watcher] No '{since_key}' timestamp in last_updated.json"
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
        sys.exit(1)
    else:
        print("Conclusion: no changes detected — skipping data download.")
        sys.exit(0)
