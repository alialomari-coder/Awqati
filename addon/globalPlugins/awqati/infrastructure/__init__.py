"""Lazy public imports for Awqati's external-capability implementations.

NVDA ships a deliberately trimmed Python runtime. Keeping these imports lazy
prevents an optional capability from making an unrelated adapter unavailable.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

__all__ = [
	"ARABIAN_CALENDAR_DATA_VERSION",
	"ArabianCalendarDataError",
	"BundledArabianCalendarRepository",
	"BundledCalculationMethodRepository",
	"CalculationMethodDataError",
	"BundledLocationRepository",
	"BundledTimezoneProvider",
	"InvalidCountryCodeError",
	"LocationDataError",
	"InvalidSettingsDataError",
	"FIRST_PUBLISHED_SETTINGS_SCHEMA_VERSION",
	"JsonSettingsRepository",
	"SettingsMigrationRegistry",
	"SettingsRepositoryError",
	"SettingsWriteError",
	"UnsupportedSettingsSchemaError",
	"SystemNowProvider",
	"TimezoneDataError",
	"UmmAlQuraDataError",
	"UmmAlQuraProvider",
	"UnknownTimezoneError",
	"WindowsLocationAdapter",
	"normalize_location_text",
]


_EXPORT_MODULES = {
	"ARABIAN_CALENDAR_DATA_VERSION": ".arabian_calendar_repository",
	"ArabianCalendarDataError": ".arabian_calendar_repository",
	"BundledArabianCalendarRepository": ".arabian_calendar_repository",
	"BundledCalculationMethodRepository": ".calculation_method_repository",
	"CalculationMethodDataError": ".calculation_method_repository",
	"BundledLocationRepository": ".location_repository",
	"InvalidCountryCodeError": ".location_repository",
	"LocationDataError": ".location_repository",
	"InvalidSettingsDataError": ".settings_repository",
	"FIRST_PUBLISHED_SETTINGS_SCHEMA_VERSION": ".settings_repository",
	"JsonSettingsRepository": ".settings_repository",
	"normalize_location_text": ".location_repository",
	"SettingsMigrationRegistry": ".settings_repository",
	"SettingsRepositoryError": ".settings_repository",
	"SettingsWriteError": ".settings_repository",
	"UnsupportedSettingsSchemaError": ".settings_repository",
	"SystemNowProvider": ".system_time",
	"BundledTimezoneProvider": ".timezone_provider",
	"TimezoneDataError": ".timezone_provider",
	"UmmAlQuraDataError": ".ummalqura_provider",
	"UmmAlQuraProvider": ".ummalqura_provider",
	"UnknownTimezoneError": ".timezone_provider",
	"WindowsLocationAdapter": ".windows_location",
}


def __getattr__(name: str) -> Any:
	"""Load only the implementation explicitly requested by the caller."""
	try:
		module_name = _EXPORT_MODULES[name]
	except KeyError as error:
		raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from error
	value = getattr(import_module(module_name, __name__), name)
	globals()[name] = value
	return value
