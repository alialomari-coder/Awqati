"""Validated loader for Awqati's versioned calculation-method data."""

from __future__ import annotations

import json
from pathlib import Path

from ..domain import CalculationMethod, CalculationMethodDefinition, CountryMethodResolver


class CalculationMethodDataError(RuntimeError):
	"""Calculation method definitions or country mapping are invalid."""


class BundledCalculationMethodRepository:
	"""Load the small method dataset once and expose typed immutable values."""

	def __init__(self, data_root: Path | None = None) -> None:
		self._root = data_root or Path(__file__).resolve().parent.parent / "data" / "calculation_methods"
		self._loaded = False
		self._version = ""
		self._methods: dict[CalculationMethod, CalculationMethodDefinition] = {}
		self._resolver: CountryMethodResolver | None = None

	@property
	def calculation_method_data_version(self) -> str:
		self._load()
		return self._version

	@property
	def country_resolver(self) -> CountryMethodResolver:
		self._load()
		assert self._resolver is not None
		return self._resolver

	def get_method(self, method: CalculationMethod) -> CalculationMethodDefinition:
		if method is CalculationMethod.AUTO:
			raise ValueError("AUTO must be resolved with a country code first")
		self._load()
		try:
			return self._methods[method]
		except KeyError as error:
			raise CalculationMethodDataError(f"method is not defined: {method.value}") from error

	def all_methods(self) -> tuple[CalculationMethodDefinition, ...]:
		self._load()
		return tuple(self._methods[method] for method in CalculationMethod if method is not CalculationMethod.AUTO)

	def _load(self) -> None:
		if self._loaded:
			return
		try:
			methods_data = json.loads((self._root / "methods.json").read_text(encoding="utf-8"))
			countries_data = json.loads((self._root / "country_methods.json").read_text(encoding="utf-8"))
			if methods_data["schemaVersion"] != 1 or countries_data["schemaVersion"] != 1:
				raise ValueError("unsupported schema version")
			version = methods_data["calculationMethodDataVersion"]
			if not isinstance(version, str) or not version or countries_data["calculationMethodDataVersion"] != version:
				raise ValueError("data versions are empty or inconsistent")
			methods: dict[CalculationMethod, CalculationMethodDefinition] = {}
			for item in methods_data["methods"]:
				code = CalculationMethod(item["code"])
				if code in methods:
					raise ValueError(f"duplicate method: {code.value}")
				methods[code] = CalculationMethodDefinition(
					code=code, name=item["name"], fajr_angle=item["fajrAngle"],
					isha_angle=item.get("ishaAngle"),
					isha_interval_minutes=item.get("ishaIntervalMinutes"),
					isha_ramadan_interval_minutes=item.get("ishaRamadanIntervalMinutes"),
					maghrib_offset_minutes=item.get("maghribOffsetMinutes", 0),
					experimental=item.get("experimental", False),
				)
			expected = set(CalculationMethod) - {CalculationMethod.AUTO}
			if set(methods) != expected:
				raise ValueError("method definitions do not exactly match the approved method codes")
			mapping = {country: CalculationMethod(code) for country, code in countries_data["countries"].items()}
			fallback = CalculationMethod(countries_data["fallback"])
			if fallback not in methods or any(method not in methods or methods[method].experimental for method in mapping.values()):
				raise ValueError("country map references an unknown or experimental method")
			resolver = CountryMethodResolver(mapping, fallback)
		except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
			raise CalculationMethodDataError(f"Cannot read calculation method data: {error}") from error
		self._version, self._methods, self._resolver, self._loaded = version, methods, resolver, True
