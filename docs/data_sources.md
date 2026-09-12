# Awqati bundled location and timezone data

This document records how the runtime data for task 1.1 is produced. Runtime
code never downloads data. The raw inputs stay outside the repository and are
not included in the NVDA add-on.

## Location data

The inclusion set is the official GeoNames cities500 snapshot dated
2026-09-11. Arabic and English alternate names come from alternateNamesV2.
Country names and administrative labels come from countryInfo,
admin1CodesASCII, and admin2Codes. All inputs use the official GeoNames dump
at https://download.geonames.org/export/dump/.

The generated location data version is
`geonames-cities500-2026-09-11+sa-2026-09-12.1+spatial-1`. Exact source URLs and SHA-256 digests are
stored in
`addon/globalPlugins/awqati/data/locations/metadata.json`.

Task 1.2 raises the location metadata schema to version 2 and adds
`spatial-index.bin.gz`. The build tool derives this index from the same generated
city records; it introduces no additional geographic source. Each fixed-width
binary entry contains only latitude, longitude, two-letter country code, stable
GeoNames identifier, administrative rank, and population. It contains no names.
The runtime verifies its SHA-256 digest, header, schema, entry count, and
uncompressed size before scanning it. The index is loaded only for an explicit
nearest-coordinate request, and the repository then loads only the winning
country file.

GeoNames data is licensed under CC BY 4.0. The bundled NOTICE and license text
are stored beside the generated metadata.

Example generation command:

```powershell
python tools/build_locations.py --cities C:\data\cities500.zip --alternate-names C:\data\alternateNamesV2.zip --country-info C:\data\countryInfo.txt --admin1 C:\data\admin1CodesASCII.txt --admin2 C:\data\admin2Codes.txt --sa-supplement data_sources\sa_locations_supplement.v1.json --output addon\globalPlugins\awqati\data\locations --location-data-version geonames-cities500-2026-09-11+sa-2026-09-12.1+spatial-1 --source-snapshot-date 2026-09-11 --generated-at 2026-09-12
```

## Reviewed Saudi supplement

The versioned build-time source `data_sources/sa_locations_supplement.v1.json`
contains the limited Saudi corrective review dated 2026-09-12. It documents
Saudi official sources, adds 25 verified GeoNames records that are outside
`cities500`, adds verified Arabic aliases to 45 existing records, and declares
three reviewed duplicate merges. Coordinates and identifiers for additions
come unchanged from the full GeoNames Saudi country dump; official Saudi
sources establish the Arabic name and administrative identity.

`tools/build_locations.py` merges this source before country files are written.
An addition is rejected when it reuses an existing GeoNames identifier or when
normalized name plus administrative/geographic evidence indicates an existing
record. Runtime still reads one ordinary `SA.json.gz` through the global lazy
repository; there is no Saudi runtime database or network access.

Run the final duplicate audit with:

```powershell
python tools/audit_sa_locations.py --data addon\globalPlugins\awqati\data\locations\countries\SA.json.gz --supplement data_sources\sa_locations_supplement.v1.json
```

The detailed audit, limitations, coverage counts, and performance measurements
are recorded in `docs/saudi_location_corrective_review_2026-09-12.md`.
## Timezone data

TZif files are extracted from the official Python `tzdata` 2026.3 wheel,
which contains IANA release 2026c. The exact wheel URL and SHA-256 digest are
stored in
`addon/globalPlugins/awqati/data/timezones/metadata.json`. The Apache-2.0
license from the wheel is bundled as `LICENSE.txt`.

Example generation command:

```powershell
python tools/build_timezones.py --wheel C:\data\tzdata-2026.3-py2.py3-none-any.whl --output addon\globalPlugins\awqati\data\timezones --source-url https://files.pythonhosted.org/packages/e5/6d/b53b99a9f2766d095985947a5782f1702cabb129a34f7a802d7197af832f/tzdata-2026.3-py2.py3-none-any.whl --generated-at 2026-09-12
```

Both tools accept small local fixture inputs for offline tests. The ordinary
`tools/run_checks.py` command validates the tools and generated outputs but
does not download or regenerate the global database.
