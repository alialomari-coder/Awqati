"""Release metadata for the Awqati NVDA add-on."""

addon_info = {
	"addon_name": "awqati",
	"addon_summary": "Awqati",
	"addon_description": 'Awqati provides prayer times, along with sunrise, midnight and the start of the last third of the night; a clock with Zawali and Ghurubi time; and five calendars: Gregorian, Lunar Hijri and three Solar Hijri calendars. It also provides daily astronomical information and information from the traditional Arabian calendar, including Talaa periods, seasons and the Suhail year.\n\nThe add-on offers reminders for daily Wird and adhkar, information about the Qibla direction, quiet hours, and control over prayer-time alerts and alerts before and after those times.\n\nIt includes four time management tools: alarms, a stopwatch, countdown timers and a world clock, with dedicated keyboard shortcuts for controlling them and checking their status.\n\nIt includes On This Day information from Wikipedia, in Arabic and English, with direct narration and accessible web pages. The add-on supports Arabic and English.',
	"addon_version": "8.2.1",
	"addon_changelog": "Version 8.2.1 refines Arabic detailed current-weather punctuation, natural dry-period wording across midnight, and the maximum hourly rain probability wording for available hours. Version 8.0.2 updates weather documentation, preserves the last successful text report without fetching on open, and refines forecast wording and zero rain repetition. Version 8.0.1 improves bilingual weather reports, daily-information detail, local city names, day/night descriptions, hourly coverage, copy report and direct weather settings. Version 8.0.0 adds optional Open-Meteo weather, current conditions, daily and hourly forecasts, customizable units, accessible reports, and an optional daily synopsis summary. Weather is disabled by default and requires an Internet connection when enabled. Migrates 7.1.0 settings while preserving existing functions. Version 7.1 integrates the approved daily astronomical synopsis: solar transit and altitude, seasonal daylight changes, Earth-Sun distance, lunar rise/set, meridian transit and independent maximum altitude, Earth-Moon distance, and upcoming principal phases. Preserves the independent Arabian calendar, existing settings and shortcuts; fixes the report text accessible name and focus return. Version 7 adds accessible basic and advanced historical date converters, a shared result window, historical arithmetic IIc and Umm al-Qura, with an optional unassigned multi-press command. Preserves existing settings. Version 6 adds Wikipedia events, births, deaths, holidays and observances in Arabic and English, with direct narration, accessible HTML pages, original article links and daily caching; includes all four time management tools introduced in version 5. Complete rebuild of the add-on formerly known as Prayer Times, with offline prayer times, two clocks, five calendars, Qibla, astronomy, the Arabian calendar, alerts, adhkar, diagnostics, and optional manual network services.",
	"addon_author": "ali alomari <alialomary@gmail.com>",
	"addon_url": "https://github.com/alialomari-coder/Awqati",
	"addon_sourceURL": "https://github.com/alialomari-coder/Awqati",
	"addon_docFileName": "readme.html",
	"addon_minimumNVDAVersion": "2026.1.0",
	"addon_lastTestedNVDAVersion": "2026.3.1",
	"addon_updateChannel": "stable",
	"addon_license": "GPL-2.0-or-later",
	"addon_licenseURL": "https://www.gnu.org/licenses/old-licenses/gpl-2.0.html",
}

pythonSources = ["addon/globalPlugins/awqati/**/*.py"]
i18nSources = pythonSources + ["buildVars.py"]
excludedFiles = ["**/__pycache__/**", "**/*.pyc", "**/*.pyo"]
baseLanguage = "en"
markdownExtensions = []
brailleTables = {}
symbolDictionaries = {}
speechDictionaries = {}
