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

Task 2.2 implements the five calendars entirely offline. Calendar identity is
explicit and no language or locale selects an algorithm.

### Calendar identities and version fields

The identifiers are `GREGORIAN`, `HIJRI_UMM_AL_QURA`,
`SAUDI_SOLAR_HIJRI`, `PERSIAN_SOLAR_HIJRI`, and
`AFGHAN_SOLAR_HIJRI`. Each has a separate provider contract. Providers share
only neutral offset/month validation helpers.

`hijriDataVersion` belongs only to the lunar Umm al-Qura lookup table. The Saudi, Persian, and Afghan solar calendars expose an independent `algorithmVersion`. They do not expose a `dataVersion` unless a real versioned table is introduced later. The lunar Umm al-Qura provider and Saudi solar-Hijri provider remain independent even when Saudi reference material informs both.

### Umm al-Qura lunar and Saudi Solar Hijri

The lunar provider uses the `UMALQURA_MONTHLENGTH` table in Unicode ICU 78.3,
tag `release-78.3`, file `icu4c/source/i18n/islamcal.cpp`. The pinned raw URL is
`https://raw.githubusercontent.com/unicode-org/icu/release-78.3/icu4c/source/i18n/islamcal.cpp`
and its SHA-256 is
`a665b4eed397fc890786a27d27e80c754f71620101d79bc6a2b1bfa7d00bb6cb`.
The source snapshot is the ICU 78.3 release published in March 2026.

`tools/build_ummalqura.py` verifies that source digest, extracts the 301
12-bit masks unchanged, and writes the runtime table and metadata. Bit 11 is
Muharram and a set bit means a 30-day month; an unset bit means 29 days. The
runtime range is 1300 through 1600 AH, corresponding to 1882-11-12 through
2174-11-25 Gregorian. Its `hijriDataVersion` is
`icu-78.3-islamic-umalqura-1300-1600`; the generated
`month_lengths.json` SHA-256 is
`945c917667ce7f610ff12fa406ddff8969f1ecff13168dfcf550a58de2884adc`.
Runtime verifies this digest and never reads the network or falls back to a
civil/tabular Hijri calendar outside the table.

ICU 78.3 is redistributed under the Unicode License v3. The license and a
specific derivation notice are bundled beside the table. The raw C++ input is
not included in the add-on.

The `SAUDI_SOLAR_HIJRI` provider is a different algorithm and identity. It
never reads the lunar table or calls the lunar provider. Its version is
`awqati-saudi-solar-1-mizan-23-september-v1`. It starts 1 al-Mizan on
23 September; the first five months have 30 days, al-Hut has 29 days or 30
when the corresponding February in Gregorian year `solarYear + 622` is leap,
and the final six months have 31 days.

Saudi references retained by the specification: https://www.mof.gov.sa/en/help/faq/Pages/FAQ_008.aspx, https://www.uqn.gov.sa/details?p=19215, https://www.uqn.gov.sa/decisions-and-regulations/royal-decrees/4000899, and https://astronomycenter.net/article/gadi_error.html.

### Persian Solar Hijri

The implementation is derived from ICU 78.3
`icu4c/source/i18n/persncal.cpp`, SHA-256
`31e7e93bb7dc1e4436c58ffd44fd1ed2686ceb79228b8d989f6573ec15ed5f45`.
Its version is `icu-78.3-persian-33-year-1304-1468`. Awqati applies ICU's
`(25 * year + 11) mod 33 < 8` leap rule and Julian-day epoch only in the
documented 1304..1468 range. ICU's published correction list begins at 1502,
so no correction entry falls inside Awqati's range. The provider rejects both
sides of the range and does not use a 2820-year cycle or an Afghan fallback.

Primary references:

- Iranian 1925 calendar law transcription: https://fa.wikisource.org/wiki/قانون_تبدیل_بروج_به_ماههای_فارسی_از_نوروز_۱۳۰۴_شمسی
- ICU `PersianCalendar` documentation and ICU 78.3 release: https://unicode-org.github.io/icu-docs/apidoc/dev/icu4j/com/ibm/icu/util/PersianCalendar.html and https://github.com/unicode-org/icu/releases/

### Afghan Solar Hijri

The Afghan provider follows the normative locale requirement published through
UNDP/Unicode: Solar Hijri year `x` is leap exactly when Gregorian year `x+621`
is leap, anchored by 1 Hamal 1382 = 21 March 2003. Its version is
`undp-unicode-2003-afghanistan-x-plus-621-anchor-1382-v1`. Unsupported Python
`datetime` dates are rejected explicitly. It does not call or fall back to the
Persian provider. A pinned cross-provider test uses 20 March 2029: ICU Persian
is 1 Farvardin 1408 while the Afghan rule is 30 Hoot 1407.

Primary reference: https://www.unicode.org/L2/L2003/03148-af-locales.pdf

### Localized month names

CLDR 48.2 is the localization cross-reference for Persian and Afghan month
names. The Arabic product resources use the spellings fixed by the Awqati
specification, including `سنبلة` and `ميزان`; English transliterations remain
separate resources. Resource selection never changes the provider. The bundled
Unicode License v3 also covers any CLDR-derived spelling data used here.

Reference: https://cldr.unicode.org/index/downloads/cldr-48 and the release-48-2 locale data at https://github.com/unicode-org/cldr/tree/release-48-2/common/main

### Reproducibility and licensing

Source and algorithm identifiers are pinned in runtime metadata or provider
properties and asserted by tests. No calendar runtime path or normal test
requires network access.
