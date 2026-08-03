# OSWM metadata generation

OSWM nodes publish a `metadata/` directory beside the existing `data/`
directory. The data layout is not migrated or rewritten. Metadata generation is
a final, global pipeline pass that observes the completed data tree and writes
deterministic JSON records.

```text
data/                         metadata/
├── index.json                ├── index.json
├── processed/                ├── processed/
│   ├── index.json            │   ├── index.json
│   └── sidewalks.parquet     │   └── sidewalks.parquet.metadata.json
└── routing/                  └── routing/
    ├── index.json                ├── index.json
    └── metadata.json             └── metadata.json.metadata.json
```

Every mirrored `index.json` is a catalogue or collection record. Every other
data file keeps its complete filename and gains `.metadata.json`, avoiding
collisions between files such as `index.html` and `index.json`.

## Generate and validate

Run these commands from the node root:

```bash
python oswm_codebase/metadata/metadata_generation.py
python oswm_codebase/metadata/metadata_generation.py --validate-only --verify-checksums
```

The generator:

- reads node identity from `config.py`;
- reads node coverage from `data/boundaries/infos.json`;
- uses `data/updates/registry.json` for stable temporal metadata;
- creates collection and asset records with HTTP links, media types, sizes, and
  SHA-256 checksums;
- removes stale records only when they identify this generator as their owner;
- preserves unknown or manually managed JSON files;
- validates that each recorded distribution still exists.

The output is deterministic. Running it twice without changing the data,
configuration, registry, or codebase revision produces the same JSON content.

## Standards profile

The records use the **OSWM Metadata Profile 1.0**, a JSON application profile
with conceptual alignment to:

| Record section | Standards basis | Applicability |
|---|---|---|
| Identification, extent, responsibility, distribution | ISO 19115-1:2014 | Geographic and mixed records |
| Acquisition and processing lineage | ISO 19115-2:2019 | Geographic and mixed records |
| Quality scope and reporting statement | ISO 19157-1:2023 | Geographic and mixed records |
| Feature-catalogue concepts | ISO 19110:2016 | Geographic feature resources and containing catalogues |
| Cross-domain descriptions | ISO 15836-1:2017 | Every record |

Each record declares its profile `domain` as `geographic`, `non-geographic`, or
`mixed`. Non-geographic products such as status pages and rule files do not
claim alignment with the geographic metadata standards.

The implementation does not reproduce ISO schemas or claim conformance to the
ISO 19115-3 XML encoding. Its fields are documented and validated by
`schemas/oswm-metadata.schema.json`. This keeps OSWM browser-native while
leaving room for later ISO XML, finalized ISO JSON, OGC API Records, or DCAT
exporters.

## API discovery

`datahub/API/generate_api.py` publishes `metadata/` as a first-class API
deliverable. Data endpoints include a link to their corresponding metadata
record, and `metadata/index.json` is the catalogue entry point for a node.
