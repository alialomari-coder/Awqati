# Awqati data sources and attribution

This document distinguishes data distributed in the Awqati package from algorithm references, optional network providers, and material supplied by the project owner. Runtime prayer, clock, calendar, Qibla, astronomy, and Arabian-calendar functions do not require network access.

## Data distributed in the package

### Locations

The location database is derived from the GeoNames `cities500` and related administrative and alternate-name exports, with reviewed additions and corrections documented in the project. GeoNames data is licensed under CC BY 4.0. The package includes the required notice and license at `globalPlugins/awqati/data/locations/NOTICE.txt` and `LICENSE-CC-BY-4.0.txt`.

Some reviewed Arabic location names were cross-checked against Wikidata and official Saudi references. The packaged location notice records the applicable attribution and the build metadata identifies the source snapshot. The detailed reproducibility record is in `docs/data_sources.md`.

### Time zones

The bundled TZif database comes from the Python `tzdata` package and the IANA Time Zone Database. The package includes its Apache-2.0 license at `globalPlugins/awqati/data/timezones/LICENSE.txt` and records the exact tzdata and IANA versions in `metadata.json`.

### Umm al-Qura and localized names

The bundled Umm al-Qura month table is derived from Unicode ICU 78.3. The Unicode License v3 and the derivation notice are included beside the table at `globalPlugins/awqati/data/calendars/ummalqura/`.

Arabic country names and calendar terminology are cross-referenced with Unicode CLDR through Babel or pinned CLDR resources. Babel and Unicode notices are included in `locale/NOTICE.txt`, `BABEL-LICENSE.txt`, and `UNICODE-LICENSE.txt`.

### Calculation methods

The packaged method profiles and country mapping implement the decisions in the Awqati 4.0 specification. PrayTimes documentation was used as a reference for astronomical formulas and conventional parameter values. The package includes a dedicated notice at `globalPlugins/awqati/data/calculation_methods/NOTICE.txt`. No PrayTimes code or network service is bundled.

### Arabian calendar

The Arabian-calendar material and its approved wording were supplied by the project owner and converted into versioned runtime data. It is traditional reference content, kept separate from scientific astronomical results. Its runtime metadata records the approved source-manifest digest.

## Algorithm and research references not distributed as third-party code

- Persian Solar Hijri: Unicode ICU Persian Calendar algorithms and the documented Iranian calendar law.
- Afghan Solar Hijri: the UNDP/Unicode Afghanistan locale specification.
- Solar events and day/night length: NOAA Solar Calculator equations.
- Seasons and lunar events: Jean Meeus, *Astronomical Algorithms*, second edition, with event checks against United States Naval Observatory publications.
- Delta T: NASA GSFC polynomial expressions by Fred Espenak and Jean Meeus.
- Qibla validation: Vincenty's WGS84 inverse method is used only as an independent test reference; runtime uses the documented spherical bearing model.

These references inform independent implementations. Their source code and research publications are not copied into the add-on.

## Optional network providers

- AlAdhan is used only when the user explicitly requests online verification of today's prayer times. Its result is shown for comparison and never silently replaces the internal calculation.
- `https://github.com/alialomari-coder/awqati-data` is the production repository for optional manual data updates. It is not the Awqati source repository or homepage.

No automatic network request is made at NVDA startup or when settings are opened.

## Detailed provenance

Exact versions, pinned URLs, hashes, transformation steps, license files, and validation rules are maintained in `docs/data_sources.md` and the metadata and notice files shipped beside each dataset.
