"""Application orchestration for versioned methods and bundled timezones."""

from __future__ import annotations

from dataclasses import replace

from ..domain import CalculationMethod, PrayerCalculationRequest, PrayerCalculator, PrayerTimes
from .ports import CalendarProvider, CalculationMethodProvider, TimezoneProvider


class PrayerService:
	"""Resolve AUTO and IANA timezone inputs before invoking the pure calculator."""

	def __init__(self, methods: CalculationMethodProvider, timezones: TimezoneProvider,
			calculator: PrayerCalculator | None = None,
			lunar_calendar: CalendarProvider | None = None) -> None:
		self._methods = methods
		self._timezones = timezones
		self._calculator = calculator or PrayerCalculator()
		self._lunar_calendar = lunar_calendar

	@property
	def calculation_method_data_version(self) -> str:
		return self._methods.calculation_method_data_version

	def calculate(self, request: PrayerCalculationRequest) -> PrayerTimes:
		effective = request.calculation_method
		if effective is CalculationMethod.AUTO:
			assert request.country_code is not None
			effective = self._methods.country_resolver.resolve(request.country_code)
		if effective is CalculationMethod.MAKKAH and request.is_ramadan is None and self._lunar_calendar is not None:
			lunar_date = self._lunar_calendar.from_gregorian(request.local_date)
			request = replace(request, is_ramadan=lunar_date.month == 9)
		return self._calculator.calculate(
			request,
			self._methods.get_method(effective),
			self._timezones.get_timezone(request.timezone_id),
			effective_method=effective,
		)
