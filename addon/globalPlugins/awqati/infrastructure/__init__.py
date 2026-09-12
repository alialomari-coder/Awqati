"""Lazy public imports for Awqati's external-capability implementations.

NVDA ships a deliberately trimmed Python runtime. Keeping these imports lazy
prevents an optional capability from making an unrelated adapter unavailable.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

__all__ = [
	"BundledLocationRepository",
	"BundledTimezoneProvider",
	"InvalidCountryCodeError",
	"LocationDataError",
	"SystemNowProvider",
	"TimezoneDataError",
	"UnknownTimezoneError",
	"WindowsLocationAdapter",
	"normalize_location_text",
]


_EXPORT_MODULES = {
	"BundledLocationRepository": ".location_repository",
	"InvalidCountryCodeError": ".location_repository",
	"LocationDataError": ".location_repository",
	"normalize_location_text": ".location_repository",
	"SystemNowProvider": ".system_time",
	"BundledTimezoneProvider": ".timezone_provider",
	"TimezoneDataError": ".timezone_provider",
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
