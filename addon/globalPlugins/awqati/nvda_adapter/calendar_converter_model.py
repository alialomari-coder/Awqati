"""Pure presentation model for the basic converter; no wx or NVDA imports."""
import calendar
from dataclasses import dataclass
from datetime import date
from typing import Callable

from ..application.historical_conversion import (
	ConversionCalendar as C, HijriMethod, HistoricalConversionService, UmmAlQuraPort,
)


class EntryError(ValueError):
	def __init__(self, code: str, field: str):
		self.code, self.field = code, field
		super().__init__(code)


def parse_number(text: str, field: str) -> int:
	"""Accept only ASCII, Arabic-Indic and Persian decimal digits, including mixes.

	Whitespace, signs, separators, bidi controls and other Unicode numerals are
	ambiguous here and rejected. Leading zeroes are harmless; zero is not a date.
	"""
	if not isinstance(text, str) or not text or len(text) > 32:
		raise EntryError("invalid_number", field)
	digits = "0123456789٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹"
	value = 0
	for character in text:
		if character not in digits:
			raise EntryError("invalid_number", field)
		value = value * 10 + digits.index(character) % 10
	if value < 1:
		raise EntryError("invalid_" + field, field)
	return value


def stepped_value(text: str, key: str, low: int, high: int, field: str) -> str:
	"""Explicit navigation clamps only on navigation, never on typing/validation."""
	if key in ("left", "right"):
		return text
	if key == "home":
		return str(low)
	if key == "end":
		return str(high)
	value = parse_number(text, field)
	delta = {"up": 1, "down": -1, "pageup": 10, "pagedown": -10}[key]
	return str(min(high, max(low, value + delta)))


def local_today(clock, timezones, location) -> date:
	"""Use Awqati's injected instant and location timezone, never UTC.date()."""
	return clock.now().value.astimezone(timezones.get_timezone(location.timezone_id)).date()


@dataclass(frozen=True)
class InputBounds:
	first: date
	last: date
	first_hijri_year: int
	last_hijri_year: int


class SimpleConversionModel:
	"""Caller supplies the conversion service and the SAME active lunar provider."""
	def __init__(self, service: HistoricalConversionService, lunar: UmmAlQuraPort,
			today: Callable[[], date]):
		self.service, self.lunar, self.today = service, lunar, today
		self.source = C.HIJRI

	@property
	def target(self):
		return C.GREGORIAN if self.source is C.HIJRI else C.HIJRI

	def bounds(self):
		try:
			first = self.lunar.first_supported_gregorian_date
			last = self.lunar.last_supported_gregorian_date
			return InputBounds(first, last, self.lunar.from_gregorian(first).year,
				self.lunar.from_gregorian(last).year)
		except (AttributeError, OSError, RuntimeError, ValueError, TypeError):
			raise EntryError("reference_data_error", "year") from None

	def current(self):
		try:
			civil = self.today()
			bounds = self.bounds()
			if not bounds.first <= civil <= bounds.last:
				raise EntryError("ummalqura_out_of_range", "year")
			if self.source is C.GREGORIAN:
				return {"day": str(civil.day), "month": str(civil.month), "year": str(civil.year)}
			result = self.service.convert(C.GREGORIAN, C.HIJRI, year=civil.year,
				month=civil.month, day=civil.day, hijri_method=HijriMethod.UMM_AL_QURA)
			if not result.successful:
				raise EntryError(result.error.code, result.error.field)
			return {field: str(getattr(result.converted, field)) for field in ("day", "month", "year")}
		except EntryError:
			raise
		except (AttributeError, OSError, RuntimeError, ValueError, TypeError, KeyError):
			raise EntryError("reference_data_error", "year") from None

	def limits(self, field, values):
		if field == "month":
			return (1, 12)
		if field == "year":
			bounds = self.bounds()
			return ((bounds.first_hijri_year, bounds.last_hijri_year) if self.source is C.HIJRI
				else (bounds.first.year, bounds.last.year))
		try:
			year = parse_number(values["year"], "year")
			month = parse_number(values["month"], "month")
			if not 1 <= month <= 12:
				return None
			length = (self.lunar.month_length(year, month) if self.source is C.HIJRI
				else calendar.monthrange(year, month)[1] if year <= 9999 else None)
			return (1, length) if length else None
		except (EntryError, AttributeError, OSError, RuntimeError, ValueError, TypeError):
			return None

	def navigate(self, field, text, key, values):
		if key in ("left", "right"):
			return text
		limits = self.limits(field, values)
		if limits is None:
			raise EntryError("date_context_required", "month")
		return stepped_value(text, key, *limits, field)

	def convert(self, values):
		parsed = {field: parse_number(values[field], field) for field in ("day", "month", "year")}
		try:
			result = self.service.convert(self.source, self.target, **parsed,
				hijri_method=HijriMethod.UMM_AL_QURA)
		except (AttributeError, OSError, RuntimeError, ValueError, TypeError):
			raise EntryError("reference_data_error", "day") from None
		if not result.successful:
			field = result.error.field
			if field not in values:
				field = "year" if "range" in result.error.code else "day"
			raise EntryError(result.error.code, field)
		return result
