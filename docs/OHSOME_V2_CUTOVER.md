# OHSOME v1 cutover
HeiGIT retires v1 after 2026-11-30. Daily jobs use current OpenStreetMap via
OSMnx/Overpass and fall back to Geofabrik snapshots, without an OHSOME key.
They compare their acquired data to the previous node snapshot and regenerate
when data, core code, or required outputs differ. The completeness denominator
is still refreshed on unchanged pedestrian runs so road-only edits are not lost.
A manual forced rebuild can still rebuild from cached raw files; it does not claim to have checked upstream.

Existing completeness history and watcher RSS are retained. Watcher edit-count
charts and changeset feeds are archival; snapshot changes are not edit counts.
Three confirmed synthetic zero dates in Sulbiate are marked unavailable. Nothing
else is removed merely because its measured values are zero.

## Optional historical completeness
Create a free key in the [HeiGIT account dashboard](https://account.heigit.org/).
Store it in the local environment as `OHSOME_API_KEY` (or in Actions Secrets if
you set up a workflow to run the command). Never commit it, echo it, or pass it
as a command-line argument. From an isolated node checkout with the build engine
at `oswm_codebase/`, run:

    python oswm_codebase/data_quality/completeness/completeness_runner.py --history-date 2026-08-01

One date uses one metadata request and up to three clipped extracts, not one
request per tile. V2 no longer has v1's grouped-boundary endpoint. Tile lengths
are measured locally from the dated geometry. A failed extraction does not
replace the existing history or chart. The historical chart measures the
historical OSM data; this does not restore live contributor or deletion metrics.

The extraction AOI encloses the full selected zoom-17 tiles, including their
parts beyond the node bounding box. Each length is measured from dated line
geometries clipped to its selected zoom-17 tile in local UTM, then summed at
coarser zooms. This is not equivalent to v1's full zoom-15 totals allocated to
children using current geometry. The timeline labels v2 dates separately;
`metadata.snapshot_methods` in `data.json` records each v2 date's AOI, filters,
timestamp, projection and grid method. Cite that method separately from archive
values in analyses. Backfill fills gaps only and will not overwrite an existing
historical observation.

The free tier allows 15 requests per sliding minute and a separate daily
quota. Serialize backfills sharing one account to avoid bursts, and stop on
429 or quota-exceeded 403. An eligible academic or nonprofit deployment can
apply for the collaborative plan via the HeiGIT account dashboard.

## Release gate
Use a pinned, non-publishing node preview first. Verify current live acquisition
and both cold and warm completeness. Capture provider, source date and (for
Geofabrik) checksum, cache hit, cold-transfer duration, and parsing duration
from the acquisition metadata and logs, then validate the full node artifact and
the archived timeline. Test historical backfill with a real key before calling
it production-verified. Merging the core's main branch changes thin-node
scheduled builds: do not merge before canary acceptance. Keep current provider
failure distinct from a successful check that found no changes.
