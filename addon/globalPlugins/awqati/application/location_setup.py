"""Side-effect-free location selection used by first run and settings drafts."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math

from ..domain import Coordinates, Location, LocationDetectionFailure, LocationKind, StoredLocation
from .ports import (
	CoordinateProvider,
	CountryInfo,
	LocationDetectionError,
	LocationMatch,
	LocationRepository,
	TimezoneProvider,
)


@dataclass(frozen=True, slots=True)
class LocationSelectionResult:
	location: StoredLocation | None = None
	failure: LocationDetectionFailure | None = None


class CustomLocationValidationError(ValueError):
	"""One neutral custom-location input failure with deterministic field focus."""

	def __init__(self, field: str, code: str) -> None:
		super().__init__(f"{field}: {code}")
		self.field = field
		self.code = code


class LocationSetupService:
	"""Resolve draft locations without publishing events or writing settings."""

	def __init__(self, repository: LocationRepository, timezones: TimezoneProvider,
			coordinate_provider: CoordinateProvider) -> None:
		self._repository = repository
		self._timezones = timezones
		self._coordinate_provider = coordinate_provider

	def countries(self) -> tuple[CountryInfo, ...]:
		return self._repository.countries()

	def search(self, country_code: str, query: str, limit: int = 20) -> tuple[LocationMatch, ...]:
		return self._repository.search(country_code, query, limit)

	def browse(self, country_code: str, limit: int = 40) -> tuple[LocationMatch, ...]:
		return self._repository.browse(country_code, limit)

	def timezone_ids(self) -> tuple[str, ...]:
		return self._timezones.timezone_ids()

	def selected(self, country_code: str, location_id: str) -> StoredLocation:
		match = self._repository.get(country_code, location_id)
		if match is None:
			raise ValueError(f"Unknown location identity: {country_code}/{location_id}")
		self._timezones.get_timezone(match.location.timezone_id)
		return StoredLocation(LocationKind.SELECTED, match.location, match.country_code)

	def custom(self, name: str, latitude: str | float, longitude: str | float,
			timezone_id: str) -> StoredLocation:
		if not isinstance(name, str) or not name.strip():
			raise CustomLocationValidationError("name", "required")
		clean_name = name.strip()
		try:
			latitude_value = float(latitude)
		except (TypeError, ValueError) as error:
			raise CustomLocationValidationError("latitude", "invalidNumber") from error
		if not math.isfinite(latitude_value) or not -90.0 <= latitude_value <= 90.0:
			raise CustomLocationValidationError("latitude", "outOfRange")
		try:
			longitude_value = float(longitude)
		except (TypeError, ValueError) as error:
			raise CustomLocationValidationError("longitude", "invalidNumber") from error
		if not math.isfinite(longitude_value) or not -180.0 <= longitude_value <= 180.0:
			raise CustomLocationValidationError("longitude", "outOfRange")
		if not isinstance(timezone_id, str) or not timezone_id.strip():
			raise CustomLocationValidationError("timezone", "required")
		clean_timezone = timezone_id.strip()
		coordinates = Coordinates(latitude_value, longitude_value)
		try:
			self._timezones.get_timezone(clean_timezone)
		except ValueError as error:
			raise CustomLocationValidationError("timezone", "invalidTimezone") from error
		identity_source = "\0".join((
			clean_name,
			format(coordinates.latitude, ".17g"),
			format(coordinates.longitude, ".17g"),
			clean_timezone,
		))
		identifier = "custom:" + hashlib.sha256(identity_source.encode("utf-8")).hexdigest()[:24]
		location = Location(identifier, clean_name, coordinates.latitude, coordinates.longitude, clean_timezone)
		return StoredLocation(LocationKind.CUSTOM, location)

	def detect(self) -> LocationSelectionResult:
		"""Run only for an explicit caller; UI callers put this method on a worker."""

		try:
			coordinates = self._coordinate_provider.get_coordinates()
			validated = Coordinates(float(coordinates.latitude), float(coordinates.longitude))
			match = self._repository.nearest(validated.latitude, validated.longitude)
			self._timezones.get_timezone(match.location.timezone_id)
		except LocationDetectionError as error:
			return LocationSelectionResult(failure=error.failure)
		except ValueError:
			return LocationSelectionResult(failure=LocationDetectionFailure.INVALID_COORDINATES)
		except (ArithmeticError, AttributeError, OSError, RuntimeError, TypeError):
			return LocationSelectionResult(failure=LocationDetectionFailure.API_ERROR)
		return LocationSelectionResult(
			location=StoredLocation(LocationKind.SELECTED, match.location, match.country_code),
		)
