"""External capabilities currently required by the application layer."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import tzinfo
from typing import Protocol, runtime_checkable

from ..domain import Instant, Location


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


@runtime_checkable
class TimezoneProvider(Protocol):
	"""Resolve IANA keys without relying on host timezone data."""

	@property
	def tz_data_version(self) -> str:
		...

	def get_timezone(self, timezone_id: str) -> tzinfo:
		...
