# Vendored validation schemas

The `catalog-spec/`, `collection-spec/` and `item-spec/` JSON schemas are
unmodified copies from https://github.com/radiantearth/stac-spec at tag
`v1.1.0`, commit `ec002bb93dbfa47976822def8f11b2861775b662`. Their Apache 2.0
license is included in `LICENSE`.

`geojson/Feature.json` and `geojson/Geometry.json` were retrieved from
https://geojson.org/schema/ on 2026-09-29. They are published by
https://github.com/geojson/schema (source inspected at
`268ba0af5f8f2c455dd0032caca10403b8bf74cc`). Their MIT license is included in
`geojson/LICENSE`.

These copies make node validation and CI independent of remote schema servers.
`metadata/stac_validation.py` registers retrieval URLs as well as declared IDs:
upstream `common.json` declares an ID ending in `commonjson`.

To update, choose a released STAC version, replace the entire schema set and
licenses, and run the STAC regression tests and client traversal before
changing the exporter's declared version.
