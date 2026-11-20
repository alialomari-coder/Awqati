"""Advanced presentation policy, reusing the approved numeric-entry behavior."""
from dataclasses import replace

from .calendar_converter_model import SimpleConversionModel, EntryError, parse_number
from ..application.historical_conversion import ConversionCalendar as C, HijriMethod
from ..domain import historical_calendars as historical


class AdvancedConversionModel(SimpleConversionModel):
	def __init__(self, service, lunar, today):
		super().__init__(service, lunar, today)
		self.target = C.GREGORIAN
		self.method = HijriMethod.IIC

	@property
	def target(self):
		return self._target

	@target.setter
	def target(self, value):
		self._target = value

	@property
	def effective_method(self):
		return self.method if C.HIJRI in (self.source, self.target) else None

	def current(self):
		try:
			civil = self.today()
			result = self.service.convert(C.GREGORIAN, self.source, year=civil.year,
				month=civil.month, day=civil.day,
				hijri_method=self.method if self.source is C.HIJRI else None)
			self._check(result)
			return {field: str(getattr(result.converted, field)) for field in ("day", "month", "year")}
		except (AttributeError, OSError, RuntimeError, ValueError, TypeError) as error:
			if isinstance(error, EntryError):
				raise
			raise EntryError("reference_data_error", "year") from None

	def limits(self, field, values):
		if field == "month":
			return (1, 12)
		if self.source is C.HIJRI and self.method is HijriMethod.UMM_AL_QURA:
			return super().limits(field, values)
		if field == "year":
			# The service owns the closed supported interval, including partial years.
			result = self.service.convert(self.source, self.source, year=1, month=1, day=1,
				hijri_method=self.method if self.source is C.HIJRI else None)
			bounds = result.source_bounds
			if bounds is None:
				raise EntryError("reference_data_error", "year")
			return bounds.first.year, bounds.last.year
		try:
			year = parse_number(values["year"], "year")
			month = parse_number(values["month"], "month")
			identity = {C.HIJRI: historical.HistoricalCalendar.HIJRI_IIC,
				C.GREGORIAN: historical.HistoricalCalendar.GREGORIAN,
				C.JULIAN: historical.HistoricalCalendar.JULIAN}[self.source]
			return (1, historical.month_length(identity, year, month))
		except (EntryError, historical.HistoricalCalendarError):
			return None

	@staticmethod
	def _check(result):
		if not result.successful:
			field = result.error.field
			if field not in ("day", "month", "year"):
				field = "year" if "range" in result.error.code else "day"
			raise EntryError(result.error.code, field)

	def convert(self, values):
		parsed = {field: parse_number(values[field], field) for field in ("day", "month", "year")}
		try:
			result = self.service.convert(self.source, self.target, **parsed, hijri_method=self.effective_method)
		except (AttributeError, OSError, RuntimeError, ValueError, TypeError):
			raise EntryError("reference_data_error", "day") from None
		self._check(result)
		return result


def reversed_result(result):
	"""Reverse an immutable successful conversion snapshot without reloading data.

	Both dates already denote the same RD under the captured reference. Swapping
	these proven endpoints preserves the exact reference/version even if the
	active provider changes while the result is open. Two reversals are identity.
	"""
	if not result.successful or result.original is None or result.converted is None:
		raise ValueError("A successful conversion snapshot is required")
	value = result.converted
	request = replace(result.request, source=value.calendar, target=result.original.calendar,
		year=value.year, month=value.month, day=value.day)
	return replace(result, request=request, original=value, converted=result.original,
		source_bounds=result.target_bounds, target_bounds=result.source_bounds)
