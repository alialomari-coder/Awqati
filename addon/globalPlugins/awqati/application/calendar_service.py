"""Application orchestration for local civil dates and explicit calendar providers."""

from __future__ import annotations

from datetime import date
from typing import Iterable

from ..domain import CalendarId, CalendarReading, InvalidHijriAdjustmentError, Location, UnsupportedCalendarError
from .ports import CalendarProvider, NowProvider, TimezoneProvider


class CalendarService:
	"""Read the local day and coordinate independently injected calendar providers."""

	def __init__(self, clock: NowProvider, timezones: TimezoneProvider,
			providers: Iterable[CalendarProvider]) -> None:
		self._clock = clock
		self._timezones = timezones
		self._providers: dict[CalendarId, CalendarProvider] = {}
		for provider in providers:
			if not isinstance(provider.calendar_id, CalendarId):
				raise TypeError("provider calendar_id must be a CalendarId")
			if provider.calendar_id in self._providers:
				raise ValueError(f"duplicate provider for {provider.calendar_id.value}")
			self._providers[provider.calendar_id] = provider

	def provider(self, calendar_id: CalendarId) -> CalendarProvider:
		if not isinstance(calendar_id, CalendarId):
			raise UnsupportedCalendarError("calendar_id must be a supported CalendarId")
		try:
			return self._providers[calendar_id]
		except KeyError as error:
			raise UnsupportedCalendarError(f"no provider for {calendar_id.value}") from error

	def read(self, location: Location, calendar_id: CalendarId,
			*, hijri_adjustment: int = 0) -> CalendarReading:
		zone = self._timezones.get_timezone(location.timezone_id)
		local_date = self._clock.now().value.astimezone(zone).date()
		return self.read_date(local_date, calendar_id, hijri_adjustment=hijri_adjustment)

	def read_date(self, local_date: date, calendar_id: CalendarId,
			*, hijri_adjustment: int = 0) -> CalendarReading:
		_validate_adjustment(hijri_adjustment)
		gregorian = self.provider(CalendarId.GREGORIAN).from_gregorian(local_date)
		lunar_provider = self.provider(CalendarId.HIJRI_UMM_AL_QURA)
		lunar_base = lunar_provider.from_gregorian(local_date)
		if hijri_adjustment:
			add_days = getattr(lunar_provider, "add_days", None)
			if add_days is None:
				raise TypeError("Umm al-Qura provider must support explicit day adjustment")
			lunar_visible = add_days(lunar_base, hijri_adjustment)
		else:
			lunar_visible = lunar_base
		selected = lunar_visible if calendar_id is CalendarId.HIJRI_UMM_AL_QURA else self.provider(calendar_id).from_gregorian(local_date)
		return CalendarReading(local_date, local_date.weekday(), selected, gregorian,
			lunar_base, lunar_visible, hijri_adjustment)


def _validate_adjustment(value: int) -> None:
	if not isinstance(value, int) or isinstance(value, bool):
		raise TypeError("hijri_adjustment must be an integer")
	if not -2 <= value <= 2:
		raise InvalidHijriAdjustmentError("hijri_adjustment must be from -2 through +2")
