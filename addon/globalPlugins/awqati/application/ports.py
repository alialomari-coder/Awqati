"""External capabilities currently required by the application layer."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, tzinfo
from typing import Protocol, runtime_checkable

from ..domain import (
	ArabianCalendarReading,
	AwqatiSettings,
	CalendarDate,
	CalendarId,
	CalculationMethod,
	CalculationMethodDefinition,
	Coordinates,
	CountryMethodResolver,
	Instant,
	Location,
	LocationDetectionFailure,
)


@runtime_checkable
class ArabianCalendarRepository(Protocol):
	"""Read validated, versioned Arabian calendar data for one local day."""

	@property
	def arabian_calendar_data_version(self) -> str:
		...

	def read(self, local_date: date) -> ArabianCalendarReading:
		...


@runtime_checkable
class CalendarProvider(Protocol):
	"""Convert one explicit calendar identity without locale-based dispatch."""

	@property
	def calendar_id(self) -> CalendarId:
		...

	def from_gregorian(self, value: date) -> CalendarDate:
		...

	def to_gregorian(self, value: CalendarDate) -> date:
		...


class LocationDetectionError(RuntimeError):
	"""A typed platform-location failure safe for application orchestration."""

	def __init__(self, failure: LocationDetectionFailure, message: str = "") -> None:
		super().__init__(message or failure.value)
		self.failure = failure


@dataclass(frozen=True, slots=True)
class CountryInfo:
	"""Small country-index entry that can be read without loading city data."""

	code: str
	name: str
	city_count: int


@dataclass(frozen=True, slots=True)
class LocationMatch:
	"""A neutral location plus metadata used to distinguish search results."""

	location: Location
	country_code: str
	country_name: str
	admin1_name: str
	admin2_name: str
	population: int
	feature_code: str

	@property
	def subdivisions(self) -> tuple[str, ...]:
		return tuple(name for name in (self.admin1_name, self.admin2_name) if name)


@runtime_checkable
class NowProvider(Protocol):
	"""Provide the current instant without binding application code to a clock."""

	def now(self) -> Instant:
		"""Return the current instant."""
		...


@runtime_checkable
class LocationRepository(Protocol):
	"""Read and search bundled locations one country at a time."""

	@property
	def location_data_version(self) -> str:
		...

	def countries(self) -> tuple[CountryInfo, ...]:
		...

	def search(self, country_code: str, query: str, limit: int = 20) -> tuple[LocationMatch, ...]:
		...

	def get(self, country_code: str, location_id: str) -> LocationMatch | None:
		...

	def nearest(self, latitude: float, longitude: float) -> LocationMatch:
		...


@runtime_checkable
class TimezoneProvider(Protocol):
	"""Resolve IANA keys without relying on host timezone data."""

	@property
	def tz_data_version(self) -> str:
		...

	def get_timezone(self, timezone_id: str) -> tzinfo:
		...


@runtime_checkable
class CoordinateProvider(Protocol):
	"""Read one explicitly requested coordinate fix from an external platform."""

	def get_coordinates(self) -> Coordinates:
		...


@runtime_checkable
class CalculationMethodProvider(Protocol):
	"""Provide validated versioned calculation data."""

	@property
	def calculation_method_data_version(self) -> str:
		...

	@property
	def country_resolver(self) -> CountryMethodResolver:
		...

	def get_method(self, method: CalculationMethod) -> CalculationMethodDefinition:
		...


@runtime_checkable
class SettingsRepository(Protocol):
	"""Persist one complete validated settings graph."""

	def load(self) -> AwqatiSettings:
		...

	def save(self, settings: AwqatiSettings) -> None:
		...
