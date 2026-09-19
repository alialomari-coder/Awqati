"""Release metadata for the Awqati NVDA add-on."""

addon_info = {
	"addon_name": "awqati",
	"addon_summary": "Awqati",
	"addon_description": (
		"This add-on provides prayer times, as well as sunrise, midnight, and the last third of the night. "
		"It also provides a clock with Zawali and Ghurubi time, and five calendars: the Gregorian calendar, "
		"the lunar Hijri calendar, and three solar Hijri calendars. In addition, it provides daily astronomical "
		"information and other information derived from the Arabian calendar about the Talaa periods, seasons, "
		"and the Suhail year.\n\n"
		"It also provides alerts for daily Wird and adhkar, and guides the user toward the Qibla direction.\n\n"
		"The add-on also supports quiet hours and lets the user enable or disable prayer-time alerts and alerts "
		"before and after those times.\n\n"
		"The add-on currently supports Arabic and English."
	),
	"addon_version": "4.0.0",
	"addon_changelog": "Complete rebuild of the add-on formerly known as Prayer Times, with offline prayer times, two clocks, five calendars, Qibla, astronomy, the Arabian calendar, alerts, adhkar, diagnostics, and optional manual network services.",
	"addon_author": "ali alomari <alialomary@gmail.com>",
	"addon_url": "https://github.com/alialomari-coder/Awqati",
	"addon_sourceURL": "https://github.com/alialomari-coder/Awqati",
	"addon_docFileName": "readme.html",
	"addon_minimumNVDAVersion": "2026.1.0",
	"addon_lastTestedNVDAVersion": "2026.2.0",
	"addon_updateChannel": None,
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
