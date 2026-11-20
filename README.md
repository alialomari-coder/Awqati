# Awqati — أوقاتي

Awqati is an NVDA add-on for prayer times, timekeeping, calendars, astronomy, and weather. It brings daily information and time management tools together in interfaces designed for keyboard and screen-reader use.

**Stable release: 8.2.1.** [Release notes](https://github.com/alialomari-coder/Awqati/releases/tag/v8.2.1) · [Download Awqati 8.2.1](https://github.com/alialomari-coder/Awqati/releases/download/v8.2.1/awqati-8.2.1.nvda-addon) · [Latest release](https://github.com/alialomari-coder/Awqati/releases/latest)

## Features

- Prayer times and related times, including sunrise, midnight, and the last third of the night, with configurable calculation methods and alerts before, at, and after the selected times.
- Zawali and Ghurubi clocks, with configurable announcements and clock alerts.
- Five calendars: Gregorian, Lunar Hijri, and the Saudi, Persian, and Afghan Solar Hijri calendars. Basic and advanced date converters also support historical Hijri, Gregorian, and Julian dates.
- Daily astronomical information about the Sun, Moon, seasons, daylight, meridian transits, distances, and upcoming principal lunar phases.
- A separate traditional Arabian calendar covering Talaa periods, seasons, and the Suhail year.
- Optional current weather and daily and hourly forecasts, configurable detail and units, and accessible text reports.
- Qibla direction information based on the selected location.
- Daily Wird and adhkar reminders, configurable alerts, and quiet hours.
- Personal alarms, countdown timers, a stopwatch, and a world clock.
- On This Day events, births, deaths, holidays, and observances from Wikipedia, with direct reading and accessible web pages.

## Requirements and languages

- Windows with **NVDA 2026.1 or later**; the release manifest declares testing through **NVDA 2026.3.1**.
- **Arabic and English** interface and user documentation.
- Python is not required to install or use the add-on.

Core prayer-time, clock, calendar, Qibla, and astronomy functions work offline. Weather and Wikipedia information require Internet access when requested. Weather is disabled by default. Optional online verification and data updates also use network services. See the guides for service behavior and privacy details.

## Download, install, and upgrade

1. Download [awqati-8.2.1.nvda-addon](https://github.com/alialomari-coder/Awqati/releases/download/v8.2.1/awqati-8.2.1.nvda-addon) from the official release.
2. With NVDA running, open the downloaded file and follow NVDA's installation prompts. Alternatively, use the Add-on Store's **Install from external source** action and select the file.
3. Restart NVDA when requested. On first use, choose a location when prompted, or configure it later in Awqati settings.

To upgrade, install this package over the existing Awqati add-on and restart NVDA. Existing settings are retained by the add-on's migration support. Use Awqati's actions in the installed add-ons list to disable or remove it.

The approved package has SHA-256:

```text
ad925257005d160315bf30069fd5f51da44b103d36b5ef86f430838075db2851
```

To check a downloaded file in PowerShell, run `Get-FileHash -Algorithm SHA256 -LiteralPath 'C:\path\to\awqati-8.2.1.nvda-addon'`, replacing the example path with the actual file path.

## User guides

- [Complete English guide](addon/doc/en/readme.md)
- [الدليل العربي الكامل](addon/doc/ar/readme.md)

The same guides are included in the add-on and available through NVDA's add-on help. They document settings, keyboard shortcuts, alerts, weather, calendars, and time tools. See [the change history](changelog.md) for the development and release record. Version 4.0.0 remains available in [the release archive](https://github.com/alialomari-coder/Awqati/releases/tag/v4.0.0); intermediate versions were not published retroactively.

## Help Translate Awqati

Awqati currently supports **Arabic and English**. We welcome volunteers who would like to help bring Awqati to other languages.

Read [TRANSLATING.md](TRANSLATING.md) to find the translation files, extraction instructions, and how to coordinate and submit contributions through GitHub. Complete support for a new language also requires coordinated build and runtime changes; translated catalogs alone are not sufficient in 8.2.1. Community translation-platform integration remains a future step.

## Support and contributions

Report problems or propose improvements through [GitHub Issues](https://github.com/alialomari-coder/Awqati/issues). Include the Awqati and NVDA versions, language, steps to reproduce, and expected and actual behavior. Review diagnostic information for personal data before sharing it.

Code and documentation contributions are welcome: read [CONTRIBUTING.md](CONTRIBUTING.md) and [DEVELOPMENT_GUIDE.md](DEVELOPMENT_GUIDE.md).

## License and attribution

Awqati is maintained by **ali alomari** and released under the **GNU General Public License, version 2 or later**. See [COPYING.txt](COPYING.txt).

Bundled data and resources retain their own applicable licenses and notices. See [DATA_SOURCES.md](DATA_SOURCES.md), [detailed provenance](docs/data_sources.md), and the notices beside the bundled resources for attribution, including GeoNames, Unicode, IANA time-zone data, and the world-clock datasets. Optional weather reports credit Open-Meteo and the applicable data providers; Wikipedia content links to its original articles and licensing information.
