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
`geonames-cities500-2026-09-11`. Exact source URLs and SHA-256 digests are
stored in
`addon/globalPlugins/awqati/data/locations/metadata.json`.

GeoNames data is licensed under CC BY 4.0. The bundled NOTICE and license text
are stored beside the generated metadata.

Example generation command:

```powershell
python tools/build_locations.py --cities C:\data\cities500.zip --alternate-names C:\data\alternateNamesV2.zip --country-info C:\data\countryInfo.txt --admin1 C:\data\admin1CodesASCII.txt --admin2 C:\data\admin2Codes.txt --output addon\globalPlugins\awqati\data\locations --location-data-version geonames-cities500-2026-09-11 --source-snapshot-date 2026-09-11 --generated-at 2026-09-12
```

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
