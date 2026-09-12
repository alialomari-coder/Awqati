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
## Prayer calculation method data

Task 1.3 stores the 19 approved Awqati 4.0 methods in
`addon/globalPlugins/awqati/data/calculation_methods/methods.json` and the
ISO-country AUTO mapping in `country_methods.json`. Both files carry the
independent version `awqati-4.0-methods-1`. The Awqati specification section
12.3 is authoritative. PrayTimes documentation at
https://praytimes.org/docs/calculation is used to cross-check the astronomical
formula and conventional values, but it does not override Awqati-specific
profiles or decisions.

Update both JSON files with the same `calculationMethodDataVersion`. Every
method code must remain unique, every country target must resolve to a defined
non-experimental method, and the fallback must remain `MWL` unless the product
specification changes. Runtime calculation reads no network data. The sunrise
and sunset angle is the code-level astronomical constant 0.833 degrees; method
angles and offsets stay in the versioned data files.

The decided future default for a new user's calculation-method setting is
`AUTO`. This task does not create settings storage or UI. An `AUTO` request
remains logically `AUTO`; `CountryMethodResolver` selects a separate effective
method at calculation time, and metadata records both values.

## Calendar sources for task 2.2

This section records the sources and version boundaries approved before implementation. It does not start task 2.2 and introduces no runtime data or code.

### Calendar identities and version fields

The planned identifiers are `GREGORIAN`, `HIJRI_UMM_AL_QURA`, `SAUDI_SOLAR_HIJRI`, `PERSIAN_SOLAR_HIJRI`, and `AFGHAN_SOLAR_HIJRI`. Each has a separate provider contract. Providers may share low-level date utilities, but language, locale, or a generic solar-Hijri switch must never choose the calendar algorithm.

`hijriDataVersion` belongs only to the lunar Umm al-Qura lookup table. The Saudi, Persian, and Afghan solar calendars expose an independent `algorithmVersion`. They do not expose a `dataVersion` unless a real versioned table is introduced later. The lunar Umm al-Qura provider and Saudi solar-Hijri provider remain independent even when Saudi reference material informs both.

### Umm al-Qura lunar and Saudi Solar Hijri

The lunar `HIJRI_UMM_AL_QURA` provider will use a separately documented and versioned table of Umm al-Qura month starts. Its table version is `hijriDataVersion`. The exact table artifact, coverage, digest, and redistribution terms must be pinned during task 2.2 before code is accepted.

The `SAUDI_SOLAR_HIJRI` provider is a different algorithm and identity. Its project reference remains Saudi Umm al-Qura calendar material about the solar-Hijri dates and zodiac-day system; it never reads the lunar table or calls the lunar provider. The documented rule starts 1 al-Mizan on 23 September, uses the twelve zodiac months and their specified lengths, and derives the year boundary independently. Its metadata field is `saudiSolarHijriAlgorithmVersion`.

Saudi references retained by the specification: https://www.mof.gov.sa/en/help/faq/Pages/FAQ_008.aspx, https://www.uqn.gov.sa/details?p=19215, https://www.uqn.gov.sa/decisions-and-regulations/royal-decrees/4000899, and https://astronomycenter.net/article/gadi_error.html.

### Persian Solar Hijri

The implementation target is the arithmetic Persian calendar in ICU 78.3, restricted by Awqati to Solar Hijri years 1304 through 1468 (approximately 1925 through 2090 CE). ICU documents that its 33-year arithmetic behavior matches the official calendar over approximately this interval and warns that the commonly cited 2820-year cycle is incorrect. Awqati must reject out-of-range input explicitly; it must not silently switch algorithm, clamp, or claim perpetual official accuracy. The Iranian 1304 law defines the year as a true solar year beginning on the first day of spring; months 1-6 have 31 days, months 7-11 have 30, and Esfand has 29 or 30. ICU supplies the pinned arithmetic leap and Gregorian-conversion behavior for this bounded implementation; it is an algorithm, not versioned calendar data.

Primary references:

- Iranian 1925 calendar law transcription: https://fa.wikisource.org/wiki/قانون_تبدیل_بروج_به_ماههای_فارسی_از_نوروز_۱۳۰۴_شمسی
- ICU `PersianCalendar` documentation and ICU 78.3 release: https://unicode-org.github.io/icu-docs/apidoc/dev/icu4j/com/ibm/icu/util/PersianCalendar.html and https://github.com/unicode-org/icu/releases/

### Afghan Solar Hijri

The Afghan provider follows the normative locale requirement published through UNDP/Unicode: Solar Hijri year `x` is leap when Gregorian year `x+621` is leap, anchored by 1 Hamal 1382 = 21 March 2003. The document states that Afghan and Iranian leap handling can differ, so results must not be normalized to the Persian provider. Unsupported dates are rejected explicitly. Hamal through Sonbola have 31 days, Mizan through Dalw have 30, and Hoot has 29 or 30. The anchor plus the published leap rule defines local Gregorian conversion; this is a fixed algorithm rather than a runtime data table.

Primary reference: https://www.unicode.org/L2/L2003/03148-af-locales.pdf

### Localized month names

CLDR 48.2 is the localization reference for Persian and Afghan month names. The Arabic product resources deliberately use the approved display spellings recorded in the Awqati specification, including `سنبلة` and `ميزان`; the native `fa_AF` forms and English transliterations remain separate resources. Resource selection never changes the provider.

Reference: https://cldr.unicode.org/index/downloads/cldr-48 and the release-48-2 locale data at https://github.com/unicode-org/cldr/tree/release-48-2/common/main

### Reproducibility and licensing

Implementation must pin source/algorithm identifiers in metadata and tests. No network access is allowed at runtime. Unicode/ICU and CLDR notices and licenses must be bundled when their code or data is incorporated; documentation links alone do not convert an algorithm into a runtime table.
