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

## Qibla and astronomy sources for task 2.3

Task 2.3 is entirely computational at runtime. It introduces no astronomy data
file and performs no network request. The single composite implementation
identifier is `awqati-astronomy-meeus2-noaa-1901-2099-v1`; source code exposes
it as `ASTRONOMY_ALGORITHM_VERSION` and every astronomy result repeats it in
metadata. The supported civil-year range is 1901 through 2099 inclusive. This
deliberately narrower product range keeps the stated Delta T and solar accuracy
meaningful even though some source polynomials have a wider mathematical range.

### Closed source matrix

| Required result | Pinned source and exact part | Time scale and UTC conversion | Supported range and expected accuracy | License/data/runtime status |
| --- | --- | --- | --- | --- |
| Current astronomical season | Jean Meeus, *Astronomical Algorithms*, 2nd ed., Willmann-Bell, 1998, chapter 27, tables 27.A/27.B and 27.C; season boundaries are the calculated equinox/solstice instants. USNO definitions: https://aa.usno.navy.mil/faq/asa_glossary | Meeus returns JDE in TT. Awqati subtracts Delta T from the NASA model below to obtain UTC, then compares absolute instants. | Product range 1901..2099. Meeus states the chapter-27 corrected instants are within about one minute for the modern era; tests use a 2-minute tolerance against USNO tables. | Published algorithm, implemented independently; no copied code or bundled data. Bibliographic use only. |
| Next equinox or solstice and local time | Same Meeus chapter 27 polynomial and 24-term periodic correction. “Next” means the first event whose UTC instant is strictly greater than `NowProvider.now()`; equality belongs to the new season and skips to the following event. | TT -> UTC with Delta T, followed by the existing bundled IANA timezone provider. | 1901..2099; 2-minute comparison tolerance. DST behavior is governed by bundled tzdata, not a fixed offset. | Same as above; computational only. |
| Day length | NOAA Global Monitoring Laboratory, *Sunrise/Sunset Calculations*, equations and 90.833-degree zenith definition: https://gml.noaa.gov/grad/solcalc/solareqns.PDF ; calculation notes: https://gml.noaa.gov/grad/solcalc/calcdetails.html | Solar equations use UTC Julian day and produce UTC minutes, then Awqati converts each instant through the bundled IANA zone. | 1901..2099. NOAA describes calculator results as theoretically accurate within about one minute for latitudes between +/-72 degrees and within about ten minutes outside them; atmospheric conditions can shift observed rise/set. | US-government NOAA material; computational only, no bundled table and no runtime network. |
| Night length | Same NOAA sunrise/sunset calculation. Scientific night here is the complement of apparent-sun day between one sunset and the next sunrise, using zenith 90.833 degrees; it is not a prayer high-latitude policy. | UTC instants as above; duration is calculated between absolute instants. | Same solar limits. Polar day and polar night are explicit states; no NearestLatitude, NightMiddle, OneSeventh, or AngleBased substitution is made. | Same as above. |
| Moon phase | USNO principal-phase definition (Moon minus Sun apparent ecliptic longitude at 0, 90, 180, and 270 degrees): https://aa.usno.navy.mil/faq/asa_glossary . Intermediate longitude comes from Meeus 2nd ed., chapters 25 and 47. Eight spoken phase names use equal 45-degree sectors centered on those four principal phases; the fixed half-sector boundaries are 22.5, 67.5, 112.5, 157.5, 202.5, 247.5, 292.5, and 337.5 degrees. | Positions are evaluated at UTC Julian day; the small TT/UTC difference is below the promised phase-description precision in this product range. | 1901..2099. Phase-sector classification is deterministic; longitude is expected within roughly 0.1 degree with the retained Meeus lunar terms. | Published equations implemented independently; thresholds are an explicit Awqati presentation policy derived from equal sectors, not external data. |
| Approximate Moon age | Meeus chapter 49 new-moon event algorithm. Age is defined as elapsed absolute time from the most recent calculated geocentric new moon to the requested instant, expressed in mean solar days. | Phase JDE is TT; subtract NASA Delta T to UTC before duration arithmetic. | 1901..2099. Event accuracy/tolerance is 2 minutes; the displayed age is explicitly approximate and is not elongation divided by a fixed synodic month. | Computational only; no runtime data. |
| Moon illumination | Meeus 2nd ed., chapter 48, illuminated fraction `k=(1+cos(i))/2`, with geocentric elongation and the chapter's phase-angle correction using Sun-Moon distances from chapters 25 and 47. | Evaluated for the requested UTC Julian day; returned as a fraction in [0,1]. | 1901..2099. Expected fraction agreement is within 0.01 against an independent ephemeris; display may round to one decimal percent. | Computational only; no runtime data. |
| Next new moon | Meeus chapter 49, equations 49.1 through 49.5 and the new-moon periodic correction table. The event exactly equal to now is not “next”; search requires a strictly later UTC instant. | JDE(TT) -> UTC with NASA Delta T. | 1901..2099; 2-minute reference tolerance. | Computational only. |
| Next full moon | Meeus chapter 49, equations 49.1 through 49.5 and the full-moon periodic correction table. Strictly later semantics match next new moon. | JDE(TT) -> UTC with NASA Delta T. | 1901..2099; 2-minute reference tolerance. | Computational only. |

### Time scales and Delta T

The seasonal and lunation algorithms produce Julian Ephemeris Day in
Terrestrial Time (TT). Awqati converts it to UTC with `TT - Delta T`, where
Delta T is `TT - UT1`; for this product's minute-level event precision UT1 is
treated as UTC. The model is Fred Espenak and Jean Meeus, NASA GSFC,
*Polynomial Expressions for Delta T*, revision displayed by the source page,
https://eclipse.gsfc.nasa.gov/LEcat5/deltatpoly.html. Awqati uses the published
1900..1920, 1920..1941, 1941..1961, 1961..1986, 1986..2005, and 2005..2050
pieces, plus the published 2050..2150 piece for 2050..2099. NASA documents the
complete model for years -1999 through +3000. The model is computational and
no table is redistributed. As a US-government NASA publication it introduces
no third-party runtime-code license.

### Reference provenance and tolerances

Season and principal-lunar-phase test instants are transcribed independently
from United States Naval Observatory published tables, including *Phases of the
Moon 2000-2049* (Circular 169):
https://aa.usno.navy.mil/downloads/Circular_169_coverupdate.pdf and the USNO
Astronomical Applications service at https://aa.usno.navy.mil/. Test comments
record the table and UTC instant. Solar samples are independently generated
from the NOAA calculator/equations above. Qibla tests independently cross-check
the city samples with the WGS84 inverse solution in T. Vincenty, “Direct and
Inverse Solutions of Geodesics on the Ellipsoid with Application of Nested
Equations,” *Survey Review* 23(176), 1975, pp. 88-93,
https://doi.org/10.1179/sre.1975.23.176.88. The test-only implementation is not
used by the product. Acceptance allows up to 0.5 degree for the intentional
spherical-versus-WGS84 model difference.

### Qibla calculation

The Kaaba coordinate is stored once as `KAABA_COORDINATES`: latitude
21.422487 north, longitude 39.826206 east. `QiblaService` uses the standard
spherical initial great-circle bearing
`atan2(sin(Delta lambda) cos(phi2), cos(phi1) sin(phi2) - sin(phi1) cos(phi2)
cos(Delta lambda))`, normalized to `[0, 360)`, clockwise from true north. The
coincident point and the spherical antipode are singular and raise a typed
error instead of returning NaN or an arbitrary direction. No magnetic north,
map, device orientation, sensor, or network service is involved.
