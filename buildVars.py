"""Release metadata for the Awqati NVDA add-on."""

addon_info = {
	"addon_name": "awqati",
	"addon_summary": 'Awqati: prayer times, calendars, weather, astronomical information and time tools.',
	"addon_description": 'Awqati is a comprehensive add-on for the NVDA screen reader, combining prayer times, calendars, astronomical information and time management tools. It also provides access to weather services and historical events through an accessible interface that supports Arabic and English.\n\nThe add-on provides the times of the five daily prayers, sunrise, midnight and the start of the last third of the night. It allows users to configure alerts for the start of prayer times and Iqama, and to set alerts before and after prayers. It also provides Zawali and Ghurubi time, as well as the Qibla direction.\n\nIt supports five calendars: Gregorian, Lunar Hijri, Saudi Solar Hijri, Persian Solar Hijri and Afghan Solar Hijri, along with tools for converting dates between the different calendars.\n\nThe add-on provides daily astronomical information, as well as information from the traditional Arabian calendar.\n\nIts features include reminders for adhkar and daily Wird, configurable quiet hours, and a range of time management tools, including personal alarms, countdown timers, a stopwatch and a world clock.\n\nIt also offers an optional weather service for checking current weather conditions and forecasts for the coming hours and days, with accessible text reports.\n\nThe add-on also includes an "On This Day" service that draws its information from Wikipedia and presents notable historical events, births, deaths, holidays and observances, either through direct narration or on web pages designed for browsing with a screen reader, with links to the original articles.',
	"addon_version": "8.2.3",
	"addon_changelog": 'Version 8.2.3\n\n- Completes the Awqati Tools menu with direct access to daily reports, date conversion, Qibla and On This Day web pages.\n- Keeps four independent clock tools and improves one-time and repeating personal alarms.\n- Shows three selectable, copyable weather reports from the menu while preserving shortcuts and saved settings.\n\nEarlier release history is available in the add-on help.',
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
