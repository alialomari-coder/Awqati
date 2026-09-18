"""Release metadata for the Awqati NVDA add-on."""

addon_info = {
	"addon_name": "awqati",
	"addon_summary": "Awqati",
	"addon_description": "Provides prayer times, Zawali and Ghurubi clocks, five calendars, adhkar and daily-Wird alerts, and Qibla direction in Arabic and English.",
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
