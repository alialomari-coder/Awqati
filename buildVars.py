"""Build metadata for the Awqati NVDA add-on scaffold.

Values marked as development placeholders must be reviewed before a release.
"""

addon_info = {
	"addon_name": "awqati",
	"addon_summary": "Awqati",
	"addon_description": "Accessible local prayer times, clocks, calendars, Qibla, daily information, alerts and adhkar in Arabic and English.",
	"addon_version": "0.5.2.2",
	"addon_changelog": "Complete task 5.2 Arabic and English localization, Islamic terminology, language direction, documentation and regression coverage.",
	"addon_author": "Awqati project (development placeholder)",
	"addon_url": None,
	"addon_sourceURL": None,
	"addon_docFileName": "readme.html",
	"addon_minimumNVDAVersion": "2026.1.0",
	"addon_lastTestedNVDAVersion": "2026.2.0",
	"addon_updateChannel": "dev",
	"addon_license": "Undecided (development placeholder)",
	"addon_licenseURL": None,
}

pythonSources = ["addon/globalPlugins/awqati/**/*.py"]
i18nSources = pythonSources + ["buildVars.py"]
excludedFiles = ["**/__pycache__/**", "**/*.pyc", "**/*.pyo"]
baseLanguage = "en"
markdownExtensions = []
brailleTables = {}
symbolDictionaries = {}
speechDictionaries = {}
