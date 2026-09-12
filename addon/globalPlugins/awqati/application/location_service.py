"""Unified orchestration of Awqati's effective runtime location."""

from __future__ import annotations

import hashlib

from ..domain import (
	Coordinates,
	Location,
	LocationChanged,
	LocationDetectionFailure,
	LocationDetectionResult,
	LocationState,
	LocationStatus,
)
from .events import EventDispatcher
from .ports import CoordinateProvider, LocationDetectionError, LocationRepository, NowProvider, TimezoneProvider


class LocationNotFoundError(ValueError):
	"""A stable bundled-location identity was not found."""


class LocationService:
	"""The sole owner of the effective location and its change event."""

	def __init__(
		self,
		repository: LocationRepository,
		timezones: TimezoneProvider,
		coordinate_provider: CoordinateProvider,
		clock: NowProvider,
		events: EventDispatcher | None = None,
		initial_location: Location | None = None,
	) -> None:
		self._repository = repository
		self._timezones = timezones
		self._coordinate_provider = coordinate_provider
		self._clock = clock
		self._events = events or EventDispatcher()
		if initial_location is not None:
			self._timezones.get_timezone(initial_location.timezone_id)
		self._current: Location | None = initial_location

	@property
	def events(self) -> EventDispatcher:
		return self._events

	@property
	def current_state(self) -> LocationState:
		if self._current is None:
			return LocationState(LocationStatus.UNSET)
		return LocationState(LocationStatus.ASSIGNED, self._current)

	def assign_selected(self, country_code: str, location_id: str) -> LocationState:
		match = self._repository.get(country_code, location_id)
		if match is None:
			raise LocationNotFoundError(f"Unknown location identity: {country_code}/{location_id}")
		self._timezones.get_timezone(match.location.timezone_id)
		self._set_current(match.location)
		return self.current_state

	def assign_custom(self, name: str, latitude: float, longitude: float, timezone_id: str) -> LocationState:
		clean_name = name.strip()
		clean_timezone = timezone_id.strip()
		coordinates = Coordinates(float(latitude), float(longitude))
		self._timezones.get_timezone(clean_timezone)
		identity_source = "\0".join(
			(clean_name, format(coordinates.latitude, ".17g"), format(coordinates.longitude, ".17g"), clean_timezone)
		)
		identifier = "custom:" + hashlib.sha256(identity_source.encode("utf-8")).hexdigest()[:24]
		location = Location(identifier, clean_name, coordinates.latitude, coordinates.longitude, clean_timezone)
		self._set_current(location)
		return self.current_state

	def clear(self) -> LocationState:
		self._set_current(None)
		return self.current_state

	def detect_and_assign(self) -> LocationDetectionResult:
		"""Perform one explicit detection; callers run this away from NVDA's main thread."""
		try:
			coordinates = self._coordinate_provider.get_coordinates()
			validated = Coordinates(float(coordinates.latitude), float(coordinates.longitude))
			match = self._repository.nearest(validated.latitude, validated.longitude)
			self._timezones.get_timezone(match.location.timezone_id)
		except LocationDetectionError as error:
			return LocationDetectionResult(LocationStatus.DETECTION_FAILED, self._current, error.failure)
		except (ArithmeticError, AttributeError, OSError, RuntimeError, TypeError, ValueError):
			return LocationDetectionResult(
				LocationStatus.DETECTION_FAILED,
				self._current,
				LocationDetectionFailure.API_ERROR,
			)
		self._set_current(match.location)
		return LocationDetectionResult(LocationStatus.ASSIGNED, match.location)

	def _set_current(self, location: Location | None) -> None:
		if location == self._current:
			return
		previous = self._current
		self._current = location
		self._events.publish(LocationChanged(self._clock.now(), previous, location))
