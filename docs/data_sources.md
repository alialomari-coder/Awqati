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
identifier is `awqati-astronomy-meeus2-noaa-1901-2099-v2`; source code exposes
it as `ASTRONOMY_ALGORITHM_VERSION` and every astronomy result repeats it in
metadata. The supported request range is the location's civil years 1901
through 2099 inclusive. Internal calculations may use only the immediately
adjacent 1900 or 2100 event when a valid endpoint request needs its preceding
season/new moon or its following season/new moon/full moon/sunrise. This
auxiliary guard does not make either adjacent year a supported request year.
For solar facts, `AstronomyService` converts noon on the requested civil date
through the location's selected IANA timezone and uses the resulting UTC date
as the neutral Domain calculation anchor. The timezone is never inferred from
longitude. This selects the solar cycle whose rise and set belong to the
requested local date, including locations across the International Date Line.
The deliberately narrower public range keeps the stated Delta T and solar
accuracy meaningful even though some source polynomials have a wider
mathematical range.

### Closed source matrix

| Required result | Pinned source and exact part | Time scale and UTC conversion | Supported range and expected accuracy | License/data/runtime status |
| --- | --- | --- | --- | --- |
| Current astronomical season | Jean Meeus, *Astronomical Algorithms*, 2nd ed., Willmann-Bell, 1998, chapter 27, tables 27.A/27.B and 27.C; season boundaries are the calculated equinox/solstice instants. USNO definitions: https://aa.usno.navy.mil/faq/asa_glossary | Meeus returns JDE in TT. Awqati subtracts Delta T from the NASA model below to obtain UTC, then compares absolute instants. | Product range 1901..2099. Meeus states the chapter-27 corrected instants are within about one minute for the modern era; tests use a 2-minute tolerance against USNO tables. | Published algorithm, implemented independently; no copied code or bundled data. Bibliographic use only. |
| Next equinox or solstice and local time | Same Meeus chapter 27 polynomial and 24-term periodic correction. “Next” means the first event whose UTC instant is strictly greater than `NowProvider.now()`; equality belongs to the new season and skips to the following event. | TT -> UTC with Delta T, followed by the existing bundled IANA timezone provider. | Requests 1901..2099; a late-2099 answer may contain the adjacent March 2100 event. Two-minute comparison tolerance. DST behavior is governed by bundled tzdata, not a fixed offset. | Same as above; computational only. |
| Day length | NOAA Global Monitoring Laboratory, *Sunrise/Sunset Calculations*, equations and 90.833-degree zenith definition: https://gml.noaa.gov/grad/solcalc/solareqns.PDF ; calculation notes: https://gml.noaa.gov/grad/solcalc/calcdetails.html | Application maps local civil noon through the selected IANA timezone to a UTC anchor date. Domain applies the solar equations to that anchor, then Application converts the resulting UTC instants back through the same zone. | 1901..2099 local civil dates, including a one-day 1900/2100 UTC anchor only when an endpoint timezone requires it. NOAA describes calculator results as theoretically accurate within about one minute for latitudes between +/-72 degrees and within about ten minutes outside them; atmospheric conditions can shift observed rise/set. | US-government NOAA material; computational only, no bundled table and no runtime network. |
| Night length | Same NOAA apparent-sun equations and 90.833-degree zenith. Scientific night is the absolute interval from the requested date's sunset to the first later upward apparent-horizon crossing. It is not defined as `24h - daylight`, and the later sunrise may fall on the same UTC date, the next date, or after a longer high-latitude interval. | Both endpoints are UTC absolute instants. Domain examines the ordered NOAA sunrise candidate for each following solar cycle instead of sampling the horizon on a fixed time grid. A normal candidate is returned immediately. At the transition into polar day, bounded minimization locates the intervening lower culmination and brackets the upward root against the following solar noon; bisection then refines that crossing. Thus a daylight or darkness interval shorter than 30 minutes cannot be skipped. | Same solar limits. Polar day and polar night remain explicit states; no NearestLatitude, NightMiddle, OneSeventh, or AngleBased substitution is made. Regression cases cover a roughly 15-minute day before polar night and a sub-30-minute night before polar day. | Same as above. |
| Moon phase | USNO principal-phase definition (Moon minus Sun apparent ecliptic longitude at 0, 90, 180, and 270 degrees): https://aa.usno.navy.mil/faq/asa_glossary . Intermediate longitude comes from Meeus 2nd ed., chapters 25 and 47. Corrected in the task 3.1 follow-up: principal names apply to the cardinal longitude values themselves; the open intervals between them are waxing crescent, waxing gibbous, waning gibbous and waning crescent. The former nearest-45-degree-sector policy was a classification defect, not the USNO definition. | Positions are evaluated at UTC Julian day; the small TT/UTC difference is below the promised phase-description precision in this product range. | 1901..2099. Classification is deterministic for the supplied approximate longitude; it does not establish exact principal-event times. Use task 2.4 for event timing. The retained longitude model is unchanged. | Published equations implemented independently; the corrected classification follows principal-angle boundaries, without broad windows or illumination rounding. Earlier equal-sector descriptions are superseded. |
| Approximate Moon age | Meeus chapter 49 new-moon event algorithm. Age is defined as elapsed absolute time from the most recent calculated geocentric new moon to the requested instant, expressed in mean solar days. | Phase JDE is TT; subtract NASA Delta T to UTC before duration arithmetic. | 1901..2099. Event accuracy/tolerance is 2 minutes; the displayed age is explicitly approximate and is not elongation divided by a fixed synodic month. | Computational only; no runtime data. |
| Moon illumination | Meeus 2nd ed., chapter 48, illuminated fraction `k=(1+cos(i))/2`, with geocentric elongation and the chapter's phase-angle correction using Sun-Moon distances from chapters 25 and 47. | Evaluated for the requested UTC Julian day; returned as a fraction in [0,1]. | 1901..2099. Expected fraction agreement is within 0.01 against an independent ephemeris; display may round to one decimal percent. | Computational only; no runtime data. |
| Next new moon | Meeus chapter 49, equations 49.1 through 49.5 and the complete new-moon periodic correction table. The event exactly equal to now is not “next”; search requires a strictly later UTC instant. | JDE(TT) -> UTC with NASA Delta T. | Requests 1901..2099; the returned event may be in adjacent 2100 for a valid late-2099 request. Two-minute ephemeris tolerance plus a subsecond coefficient-regression vector. | Computational only. |
| Next full moon | Meeus chapter 49, equations 49.1 through 49.5 and the complete full-moon periodic correction table. Strictly later semantics match next new moon. | JDE(TT) -> UTC with NASA Delta T. | Same endpoint policy and reference tolerances as next new moon. | Computational only. |

### Time scales and Delta T

The seasonal and lunation algorithms produce Julian Ephemeris Day in
Terrestrial Time (TT). Awqati converts it to UTC with `TT - Delta T`, where
Delta T is `TT - UT1`; for this product's minute-level event precision UT1 is
treated as UTC. The model is Fred Espenak and Jean Meeus, NASA GSFC,
*Polynomial Expressions for Delta T*, revision displayed by the source page,
https://eclipse.gsfc.nasa.gov/LEcat5/deltatpoly.html. Awqati uses the published
1900..1920, 1920..1941, 1941..1961, 1961..1986, 1986..2005, and 2005..2050
pieces, plus the published 2050..2150 piece for 2050..2099 requests and the
single adjacent auxiliary year 2100. The 1900 piece is likewise used only when
an endpoint request needs a preceding event. NASA documents the
complete model for years -1999 through +3000. The model is computational and
no table is redistributed. As a US-government NASA publication it introduces
no third-party runtime-code license.

### Reference provenance and tolerances

Season and principal-lunar-phase test instants are transcribed independently
from United States Naval Observatory published tables, including *Phases of the
Moon 2000-2049* (Circular 169):
https://aa.usno.navy.mil/downloads/Circular_169_coverupdate.pdf and the USNO
Astronomical Applications service at https://aa.usno.navy.mil/. Test comments
record the table and UTC instant. The complete 25-term new/full correction
arrays, powers of `E`, `Omega`, and all fourteen additional planetary arguments
were audited in one pass against Meeus chapter 49 and the independent PyMeeus
0.5.12 implementation (LGPL-3.0, used only during development; no code or
dependency is bundled): https://github.com/architest/pymeeus. The two
new-moon coefficients that differ from full moon are preserved explicitly:
`-0.00514 E sin(M' + M)` versus `-0.00515`, and
`+0.00208 E^2 sin(2M)` versus `+0.00209`. A static `k=-651` high-sensitivity
audit vector, independently tabulated from the printed chapter-49 terms, uses
a 50-millisecond regression tolerance; substituting the two full-moon values
moves the result by about 1.73 seconds. Solar samples are independently generated
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

## Arabian calendar data for task 2.4

The approved build-time source package is
`data_sources/Awqati_ArabianCalendar_Data_v1`, restored from the review copy at
`G:\ملفاتي\إضافة أوقاتي\data_sources\Awqati_ArabianCalendar_Data_v1`.
Its `arabianCalendarDataVersion` is `2026.09.13-r1`. The corrected source
manifest SHA-256 is
`218c34754010b2218776e0470b061191a5a46014fa63b1c13ecc2be44d33856f`.
The approved `arabian_calendar.json` is 71,633 bytes with SHA-256
`d43e4c1cc618ee070b31d8557f37ee9a420d31bf80edff0196a4dfda5f06e04a`.
It includes the approved marzam saying `«إذا طلع المرزم يا خراف الزم.»`.

Only three source files become runtime content under
`addon/globalPlugins/awqati/data/arabian_calendar`: the rich entity source,
the 365-day common index, and the 366-day leap index. Runtime `metadata.json`
pins their sizes and SHA-256 digests and records the source manifest digest.
The common index SHA-256 is
`b0ced103f84a4970252a1cb2b8e330949800ca221e8f4ef6cb1079d517772ec7`;
the leap index SHA-256 is
`a9b14d3cc65e9570938ff19ed27ebcdd6a22d0f3acd53e546c37079346a2309f`.
README, schemas, validation reports, research sources, and ZIP inputs remain
build-time provenance and are not packaged for users.

The runtime repository loads and validates the bundle lazily, verifies the
schema and data versions, file digests, daily continuity, entity references,
and saying assignments, then caches the parsed result. A local date on or
after 24 August uses 24 August of its year as the cycle anchor; an earlier date
uses 24 August of the previous year. If February of the following Gregorian
year has 29 days, the leap index is selected; otherwise the common index is
selected. Daily lookup is direct by `MM-DD`; runtime does not recalculate the
28 talaa boundaries or parse the files again for each request.

The owner-approved user terminology is «السنة السهيلية» or «سنة سهيل».
Heritage sayings, seasonal observations, mansion descriptions, and classical
naw material are preserved as attributed content. They are not scientific
astronomy facts and never modify prayer, qibla, calendar, or `AstronomyService`
results. Runtime uses no network and no AI, and corrupt or incompatible data
raises a typed error without fallback or guessed talaa dates.

## Solar upper transit, enhancement task 1.1 (19 November 2026)

The existing NOAA/Meeus solar terms and `_solar_noon` seed are reused.
Only the new upper transit is refined iteratively at the event instant;
the established rise/set and prayer calculations are unchanged. `SolarDay`
now carries an aware UTC transit, geometric solar-center altitude in degrees,
and an independent availability state. `AstronomyReading.solar_transit_local`
converts at the event instant using the existing bundled IANA timezone.
The supplied civil date is selected by converting adjacent UTC cycles;
missing/multiple transits and the exact geographic poles return no values.

Altitude is `90 - abs(geodetic latitude - geocentric declination at transit)`:
no refraction, solar parallax, elevation or terrain correction. Upper meridian
transit is distinguished from the slightly different instantaneous altitude
maximum of a Sun with changing declination. No text formatter is changed.

Independent validation uses NASA JPL Horizons DE441, Sun 10, airless
topocentric elevation (quantity 4), and the zero of local apparent hour angle
(quantity 42), at sea level. Raw responses, request URLs and retrieval dates
are in `docs/solar_transit_task11/`; the complete Arabic report is
`SOLAR_TRANSIT_TASK11_REPORT.md`. There are 36 cases at six sites over the four
seasons and both DST changes in Cairo, London and Sydney. Acceptance limits
are 15 seconds and 0.02 degrees; these account for compact NOAA series,
UT1/UTC differences and solar parallax, without using refraction corrections.
They are sample validation limits, not a full-century error proof.

Developer-only offline replay: `python tools/verify_solar_transit.py`.
Explicit `--fetch` refreshes reference evidence over the network; neither
this tool nor reference data is a runtime dependency of the add-on.

Primary references:
- https://ssd-api.jpl.nasa.gov/doc/horizons.html
- https://ssd.jpl.nasa.gov/horizons/manual.html#obsquan
- https://gmd-int.cmdl.noaa.gov/grad/solcalc/calcdetails.html

## Seasonal daylight and annual extremes — enhancement task 1.2 (19 November 2026)

The existing NOAA/Meeus engine is the sole runtime calculator. A shared
`solar_day_for_local_date` preserves the existing local-noon UTC anchor.
`AstronomyService.read_daylight(location)` is an opt-in API; `read()` and the
current synopsis do not request an annual scan. Execute this API on the existing
astronomy worker. A per-service LRU of four immutable annual results is keyed by
local Gregorian year, exact coordinates and actual bundled IANA zone object.

Daylight is sunset minus sunrise in UTC; the corresponding night is the first
later sunrise minus sunset in UTC, even across DST or a year boundary. Night is
not 24 hours minus daylight. Thus longest daylight and shortest night need not
share a civil date. Annual results retain independent night extrema dates and
`combined_day_night_claim_valid` explicitly gates the proposed joint wording.
No formatter or notification is added in task 1.2.

The latest solstice whose instant has elapsed is the seasonal reference. Its
local civil date supplies the comparison solar cycle. Before the instant on a
solstice date the previous solstice remains the reference; at/after the instant
the new reference applies and that date's change is zero. June is summer in the
north and winter in the south; December reverses this. Latitude zero uses the
north naming convention, not an assumed increasing/decreasing trend. `change`
is a signed timedelta (current minus reference); use its actual sign for future
wording and its absolute value for duration formatting. Fractional seconds are
retained; consumers can convert to minutes/hours without premature rounding.
The supported local-year range is 1901..2099, with auxiliary 1900/2100 only for
adjacent comparisons, the previous solstice and the next sunrise.

Every civil date in the requested Gregorian year (365 or 366) is evaluated.
Extrema are selected using complete timedeltas at Python microsecond resolution,
not a fixed solstice date or rounded clock times. `days` contains exact ties in
the retained numerical model. This is not proof of a physical equality beyond
the model's accuracy. `rounded_minute_dates` separately records equality after
round-half-up of total duration to minutes; it never controls event eligibility.
Only the first chronological exact tie date is eligible in `events_today`,
even for disjoint ties. Other dates return no event. This is eligibility data,
not a persistent announcement scheduler; repeated reads on the eligible date
return the same facts and do not themselves speak or send a notification.

Polar states return no new duration sample or seasonal change rather than
reusing legacy 0/24-hour placeholders. If any civil date has no valid complete
rise/set cycle (including a skipped local date such as Apia 2011-12-30), annual
extrema are unavailable for the whole year; `unavailable_dates` explains the
coverage. Extrema of an incomplete subset must not be presented as annual
extrema. Established SolarDay placeholders and the displayed synopsis remain
unchanged for compatibility. Prayer times and user settings are untouched.

Independent evidence: NASA JPL Horizons DE441, Sun 10, sea-level topocentric
AIRLESS solar-center elevation (quantity 4), with the same fixed conventional
-0.833 degree horizon. Three samples at seed +/-300 seconds bracket each
crossing; an independent quadratic elevation interpolation locates rise/set.
NOAA supplies brackets only, not reference positions. Raw JPL responses, request
URLs/retrieval times and all actual/reference duration differences are in
`docs/seasonal_daylight_task12`. This is not a terrain/weather prediction.

112 duration comparisons at Riyadh, London, Sydney, Kiritimati and the equator
pass 120-second daylight/night limits: maxima 16.128846 and 16.450497 seconds.
28 seasonal differences pass a 240-second limit (two duration error budgets):
maximum 25.141044 seconds. Four polar solstice cases agree with JPL hourly
samples safely above/below the horizon; these check polar classification, not
precision at a polar transition. Eight of ten extreme dates agree in the
seven-day reference windows centered on model extrema. At latitude/longitude
0/0, model June 21 vs JPL-window June 20 differs by 0.015040 seconds of daylight;
model March 20 vs JPL-window March 22 differs by 0.081049 seconds. These are
reported date disagreements on nearly flat curves, not exact ties. The extra
one-second equatorial candidate-duration check is a sensitivity diagnostic
selected after observing these differences, not an independently confirmed
date-accuracy guarantee. Runtime extrema always mean extrema of the established
engine. A complete independent annual scan and full-century validation have
not been claimed. Ordinary-site date comparisons require exact date agreement.

Developer checks (no dependency installation or package replacement):
`development_baseline/python-3.13.15/python.exe -B tools/run_seasonal_daylight_checks.py`
and offline reference replay:
`development_baseline/python-3.13.15/python.exe -B tools/verify_seasonal_daylight.py`.
Only an explicit `--fetch` contacts NASA. No task 1.1 reference suite is rerun.
Primary sources: [JPL Horizons quantities](https://ssd.jpl.nasa.gov/horizons/manual.html#obsquan),
[JPL API](https://ssd-api.jpl.nasa.gov/doc/horizons.html),
[USNO horizon definitions](https://aa.usno.navy.mil/faq/RST_defs).

## Astronomy phase 1, task 1.3 — instantaneous Earth–Sun distance

Definition: approximate simultaneous **geometric center-to-center** range
between Earth (399) and Sun (10), in km. This is neither surface separation,
an observer's topocentric range, nor an apparent/light-time-corrected range.
The low-order NOAA/Meeus orbit approximates the geocenter; lunar and planetary
perturbations are not explicitly modeled.

`sun_distance(aware_datetime) -> SunDistance` normalizes to UTC and validates
the absolute UTC year, 1901–2099 inclusive. `AstronomyService.read_sun_distance()`
reads the existing NowProvider exactly once per request; no date truncation,
daily cache, location dependency, I/O, network, or new dependency. The returned
immutable reading includes `observed_at_utc`, unrounded float `distance_km`, and
its own `awqati-sun-distance-noaa-meeus-v1` identifier. The existing daily
reading, astronomy version, synopsis, prayer times, settings, tasks 1.1/1.2,
and approved 7.0.0 package retain their contracts.

Reuse: the existing solar mean anomaly, equation of center and eccentricity
expressions were moved verbatim to private shared helpers. Their callers keep
the same operations and inputs; 7,203 exact float comparisons against the
hash-matched pre-task source found no change to apparent longitude, equation
of time or declination. All other 52 existing astronomy definitions are
structurally identical. This check is not a rerun of tasks 1.1/1.2 references.

For the existing UTC-based Julian century `T`, with mean anomaly `M`, equation
of center `C`, true anomaly `v=M+C`, and eccentricity `e`, use
`R_AU = 1.000001018 * (1-e*e) / (1+e*cos(v))` (v in degrees), then multiply by
149,597,870.7 km/au, the exact IAU 2012 conversion. This follows the established
NOAA time convention without adding a new TT conversion; that approximation
is included in the measured model errors. No distance is rounded in domain.
Sources: [NOAA/Meeus calculation details](https://gml.noaa.gov/grad/solcalc/calcdetails.html),
[NOAA solar equations implementation](https://gml.noaa.gov/grad/solcalc/main.js),
[NOAA calculation spreadsheet](https://gml.noaa.gov/grad/solcalc/NOAA_Solar_Calculations_day.xls),
[IAU 2012 resolution B2](https://www.iau.org/static/resolutions/IAU2012_English.pdf).

Presentation is opt-in and separate in `application/sun_distance_presentation.py`:
`format_sun_distance_millions(distance_km)` divides by one million and returns
one fixed decimal, no grouping, using Python's nearest rounding (ties to even).
Its 0.1 million km step is 100,000 km; maximum rounding error is 50,000 km.
This is display precision, not a claim of measurement precision. A model value
close to a rounding boundary can round differently from JPL. Future templates:

- Arabic: «وتبعد الأرض حاليًا عن الشمس نحو [المسافة المحسوبة] مليون كيلومتر».
- English: “And Earth is currently about [calculated distance] million kilometers from the Sun.”

These templates are documented only; no new text enters the current synopsis
or translation catalogs before task 3.1.

Independent validation: DE441 via [NASA JPL Horizons API](https://ssd-api.jpl.nasa.gov/doc/horizons.html),
`COMMAND=10`, `CENTER=500@399`, `EPHEM_TYPE=VECTORS`, `VEC_CORR=NONE`,
`OUT_UNITS=KM-S`, `VEC_TABLE=3`, `TIME_TYPE=UT`, ordered JD TLIST. Compare `RG`,
not observer-table light-time-corrected delta. Epoch agreement is checked for
every row. The preselected tolerance is **25,000 km** (about 0.017% of the
distance and below the 50,000 km display half-step); this is an acceptance
bound for the sample, not a proven global bound across every supported instant.

50 instants include 1901, 1950, 2000, 2026, 2050 and 2099, near perihelion,
aphelion, both equinoxes and solstices, extra monthly/near-extreme samples in
2026, same-day different hours and UTC range endpoints. No algorithm to find
precise apsis times was implemented. Per the [Horizons time documentation](https://ssd.jpl.nasa.gov/horizons/manual.html#time),
UT means UT1 before 1962 and UTC thereafter; historical samples use the same
nominal calendar/JD labels with the project's proleptic UTC convention and
are not a separate historical UTC realization. Future leap seconds are
predicted/frozen by JPL. These time conventions and low-order orbit omissions
limit the accuracy; this feature is for approximate spoken information.

All 50 passed: maximum absolute error 11,003.401456 km (2026-07-01 12:00 UT),
mean absolute error 3,823.232873 km. Full signed errors, raw response, timestamp,
request URL, response SHA-256, tests, preservation and delivery evidence are in
`docs/sun_distance_task13`. First fetching within the sandbox failed DNS;
the authorized network retry succeeded. A read of the prior synced baseline
required external filesystem access and then succeeded; it matched the
pre-edit SHA-256. Neither issue was a calculation failure.

Offline focused checks: `development_baseline/python-3.13.15/python.exe -B tools/run_sun_distance_checks.py`.
Offline raw reference replay: `development_baseline/python-3.13.15/python.exe -B tools/verify_sun_distance.py`.
Preservation check: `development_baseline/python-3.13.15/python.exe -B tools/verify_sun_distance_preservation.py`.
Only explicit `--fetch` on the reference tool contacts NASA during development.
No new UI, NVDA installation, build or general release gate is needed for this
unexposed calculation. No task 1.1/1.2 reference suite was rerun.

## Lunar horizon task 2.1 — 2026-11-19

Offline Meeus (Astronomical Algorithms, 2nd edition, chapters 12, 22, 40, 47),
ELP-2000/82 numerical tables 47.A/B (60 longitude/radius and 60 latitude terms).
Factual coefficients checked against the primary implementation at
https://raw.githubusercontent.com/architest/pymeeus/master/pymeeus/Moon.py ;
no PyMeeus library code or dependency added. Bundled coefficients are fixed;
source and coefficient SHA-256 are recorded in lunar_horizon_task21/algorithm_sources.json.
Shared Julian dates, Espenak/Meeus Delta T, supported-year and coordinate checks
remain in the existing astronomy module; the old longitude/phase path is unchanged.
The internal radial series is required for parallax and semidiameter only,
not a lunar-distance feature or output. No additional phases or culmination API.

Definition: sea-level oblate-Earth observer, flat unobstructed horizon,
topocentric geometric center altitude + instantaneous topocentric semidiameter
+ constant 34 arcmin refraction = zero. Earth equatorial radius 6378.14 km,
polar/equatorial factor .99664719, lunar mean radius 1737.4 km. TT lunar theory,
apparent equator/date coordinates with dominant nutation terms; UTC approximates
UT1 in rotation. Weather, height, dip and terrain are intentionally unmodeled.
A tangent without a sign change is neither rise nor set.

Primary independent reference and matching convention:
https://aa.usno.navy.mil/faq/RST_defs and
https://aa.usno.navy.mil/data/api . USNO API 4.0.1 supplies minute-rounded events.
Fetch dates in UTC, convert each event through the project's bundled IANA provider,
and filter by the requested local date; do not use a fixed daily offset for DST.
Saved raw responses, request URLs, saved timestamps and SHA-256 are in
`docs/lunar_horizon_task21/reference_manifest.json`. Offline replay verifies hashes,
API version, dates, coordinates, counts and time differences. Acceptance thresholds
chosen before comparison: 90 seconds ordinarily, 180 seconds at |latitude| >=65;
event counts must agree separately. 33 cases / 47 events passed; maximum absolute
error 29.445190 seconds, mean 12.952011 seconds. These are sample results,
not a guarantee at arbitrarily grazing contacts or every date in 1901–2099.
See LUNAR_HORIZON_TASK21_REPORT.md for the Arabic report and limitations.


## المهمة الفلكية 2.2 — القمر وJPL Horizons

المصدر المرجعي: [دليل NASA JPL Horizons](https://ssd.jpl.nasa.gov/horizons/manual.html).
هدف 301 من DE441، راصد أرضي طبوغرافي عند سطح البحر، `AIRLESS`، مركز
القرص، كميات 4 و5 و42 و49. جميع أيام العينة تقع بعد 1962، لذا مقياس
`UT` المرجعي هو UTC؛ محركنا يقرب UT1 بـUTC في دوران الأرض. لا نصف قطر
للقرص أو انكسار في الارتفاع المقارن، خلاف تعريف الشروق والغروب في 2.1.

الشبكة المستقلة تشمل اليوم المحلي الفعلي بدقيقة واحدة، مع شبكة ثانيتين
قرب السمت مختارة من نتائج المرجع. يستخرج H=0 العبور، ويستخرج استيفاء
قمم الارتفاعات أعلى ارتفاع مستقلاً مع فحص الطرفين. لا تستخدم معدلات
الارتفاع المقربة لتوقيت القمة القطبية المسطحة. أُبقيت سماحية 30 ثانية
و0.03 درجة المحددة قبل الجلب. نجحت الحالات الأربع عشرة: 11 عبورًا و14
قيمة قصوى؛ أقصى فرق 11.992175 ثانية و0.001228038 درجة. ليست هذه
شهادة دقة لجميع السنوات أو كل المواقع؛ نموذج Meeus لا يساوي DE441.

المصدر الحسابي هو نفس نظرية القمر ومتجه الراصد في المهمة 2.1؛ لا
إنترنت أثناء استخدام الإضافة. الردود الخام والطلبات وتواريخ الجلب
والبصمات محفوظة في `docs/lunar_transit_task22/`، والنتائج في
`comparison.json`، والتعريف والصياغات والقيود في `LUNAR_TRANSIT_TASK22_REPORT.md`.
لا إعادة لمقارنات المهام السابقة، ولا تعديل النبذة الحالية أو بدء 2.3.


## المهمة 2.3 — مسافة القمر الحالية

نصف القطر الجيومركزي من Meeus الفصل 47 ومعاملات `_lunar_terms.py`،
بإعادة استخدام `_position` القائمة دون تغيير الحساب السابق. المسافة هندسية
بين المركزين بلا زمن ضوء، وليست مسافة الراصد. المرجع DE441 في
[NASA JPL Horizons](https://ssd.jpl.nasa.gov/horizons/manual.html)،
هدف 301، مركز 500@399، VECTORS، VEC_CORR=NONE، KM-S، TIME_TYPE=UT؛
معيار المقارنة طول متجه الموضع. نجحت 41 عينة ضمن 20 كم، بأقصى فرق
7.004829 كم. السماحية محددة قبل الجلب ولا تعمم على كل السنوات.
بيانات UT قبل 1962 تاريخية UT1، بخلاف امتداد UTC الاصطلاحي في Python.
الرد الخام والطلب والبصمات والفروق: `docs/lunar_distance_task23/`.
القيود والصياغات والتشغيل في `LUNAR_DISTANCE_TASK23_REPORT.md`.


## Task 2.4: principal lunar phase instants

Shared Meeus, Astronomical Algorithms (2nd ed.), chapter 49: existing new/full
series and planetary terms retained, quarter table and signed W added. Events
are geocentric apparent longitude differences 0/90/180/270 degrees, independent
of descriptive sectors or illumination thresholds. Legacy UTC outputs unchanged.
New UTC uses IERS leap offsets for 1972–2026 only; outside this window modeled
UT is explicitly marked, with TT preserved. No runtime network or dependencies.
IERS source: https://hpiers.obspm.fr/iers/bul/bulc/Leap_Second.dat .
Definition and USNO data/API: https://aa.usno.navy.mil/faq/moon_phases ,
https://aa.usno.navy.mil/data/MoonPhases , https://aa.usno.navy.mil/data/api.html .
295 USNO minute samples retained; the original 120 s diagnostic margin failed
at 2099 (max 123.826254 s), with different inferred time extrapolation.
Primary acceptance: 96 JPL DE441 TT roots of apparent longitude difference,
90 s margin declared before retrieval; max 14.871159 s. JPL settings:
Earth center 500@399, targets 301/10, OBSERVER quantity 31, AIRLESS, TT.
Manual: https://ssd.jpl.nasa.gov/horizons/manual.html . API:
https://ssd-api.jpl.nasa.gov/doc/horizons.html . Raw responses, requests/hashes,
per-phase signed errors and diagnostics: docs/lunar_phases_task24/.
Arabic results and limitations: LUNAR_PHASES_TASK24_REPORT.md.


## Task 3.1 synopsis integration — 2026-11-19

No new scientific source, network request or ephemeris algorithm was introduced.
The presentation uses the approved services from tasks 1.1–2.4: solar upper
transit (not an altitude maximum), signed solstice-relative daylight change,
independent annual day/night extreme dates, instantaneous center-to-center
ranges, local civil-day lunar crossings, separate lunar transit and geometric
maximum, and four principal phases. Lunar end limits are not attained events.
Upcoming phase display uses task 2.4 only; legacy new/full timestamps are not
also displayed. The existing lunar age/illumination model remains unchanged.
The 1901–2099 source contracts and all previous reference limitations remain;
modeledUT phase times carry an explicit approximate ΔT notice. Presentation
rounding to minutes does not establish observational minute-level accuracy.
Heritage sources and text are untouched. See DAILY_SYNOPSIS_TASK31_REPORT.md
and docs/daily_synopsis_task31/ for generated examples and focused evidence.


## Task 3.1 corrective follow-up — 2026-11-19

Primary source checked: [USNO phase definitions](https://aa.usno.navy.mil/faq/moon_phases).
New/full/quarter phases are instantaneous principal-longitude events; crescent
and gibbous stages occupy the intervening intervals. Equal 45-degree name
sectors wrongly called 111.666 degrees first quarter. Correcting the domain
classifier changes that example to waxing gibbous without changing its
68.575% illumination, 10.082-day age or numerical ephemeris. Cardinal-angle
classification of an approximate instantaneous longitude is not a replacement
for the approved task 2.4 principal-phase event service. No new observational
precision is claimed and no astronomical reference suites were rerun.
The corrected text, targeted tests and preservation evidence are documented
in DAILY_SYNOPSIS_TASK31_CORRECTION_REPORT.md. Heritage is untouched.


## Task 3.1 final editorial closure — 2026-11-19

The owner-approved Arabic reference is stored unchanged in
`docs/daily_synopsis_task31/final_editorial/approved_ar.txt`. Generated Arabic
matches it after whitespace normalization; English follows the same meaning
and paragraph order. Only two presentation files changed. No ephemeris,
calculation service, phase definition, numeric result or heritage source was
modified. Chronological links compare actual event instants, not rounded
clocks. Phase display omits the year only when its rounded local date is in
the observation's local year. Previous scientific accuracy limits and the
modeled ΔT notice remain. See DAILY_SYNOPSIS_TASK31_FINAL_EDITORIAL_REPORT.md.
