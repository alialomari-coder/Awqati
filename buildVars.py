"""Build metadata for the Awqati NVDA add-on scaffold.

Values marked as development placeholders must be reviewed before a release.
"""

addon_info = {
	"addon_name": "awqati",
	"addon_summary": "Awqati",
	"addon_description": "Awqati development build with NVDA commands, windows and automatic alert lifecycle integration.",
	"addon_version": "0.5.1.4",
	"addon_changelog": "Correct task 5.1 localization, native repeat handling, gesture help, 12-hour periods, daily information, owner-edited Arabian calendar data and localized hour-minute prayer-state durations.",
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
