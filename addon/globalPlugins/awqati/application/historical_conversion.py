"""Explicit, unadjusted date conversion; no UI, settings or provider discovery.

Inject the SAME active Umm al-Qura provider used by the application. Omitting it
is valid for IIc and civil-only conversions, never a request for bundled data.
RD 1 denotes Gregorian 0001-01-01; bounds are closed intervals.
"""
from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Protocol

from ..domain.calendar import CalendarDate, CalendarId, CalendarOutOfRangeError
from ..domain import historical_calendars as historical


class ConversionCalendar(str, Enum):
	HIJRI = "HIJRI"
	GREGORIAN = "GREGORIAN_PROLEPTIC"
	JULIAN = "JULIAN_PROLEPTIC"


class HijriMethod(str, Enum):
	UMM_AL_QURA = "UMM_AL_QURA"
	IIC = "HIJRI_TABULAR_IIC"


class UmmAlQuraPort(Protocol):
	@property
	def metadata(self) -> dict[str, object]: ...
	@property
	def hijri_data_version(self) -> str: ...
	@property
	def first_supported_gregorian_date(self) -> date: ...
	@property
	def last_supported_gregorian_date(self) -> date: ...
	def month_length(self, year: int, month: int) -> int: ...
	def to_gregorian(self, value: CalendarDate) -> date: ...
	def from_gregorian(self, value: date) -> CalendarDate: ...


@dataclass(frozen=True)
class ConversionDate:
	calendar: ConversionCalendar
	year: int
	month: int
	day: int


@dataclass(frozen=True)
class ConversionRequest:
	source: ConversionCalendar
	target: ConversionCalendar
	year: int
	month: int
	day: int
	hijri_method: HijriMethod | None = None


@dataclass(frozen=True)
class ConversionBounds:
	min_rd: int
	max_rd: int
	first: ConversionDate
	last: ConversionDate


@dataclass(frozen=True)
class UmmAlQuraReference:
	version: str
	table_sha256: str
	source_project: str
	source_release: str
	source_url: str


@dataclass(frozen=True)
class ConversionError:
	code: str
	field: str
	stage: str
	bounds: ConversionBounds | None = None


@dataclass(frozen=True)
class ConversionResult:
	request: ConversionRequest
	original: ConversionDate | None = None
	converted: ConversionDate | None = None
	hijri_method: HijriMethod | None = None
	rd: int | None = None
	reference: UmmAlQuraReference | historical.MethodReference | None = None
	source_bounds: ConversionBounds | None = None
	target_bounds: ConversionBounds | None = None
	error: ConversionError | None = None
	common_reference: str = "RD: Gregorian 0001-01-01 = 1"

	@property
	def successful(self) -> bool:
		return self.error is None


def _historical_id(calendar: ConversionCalendar) -> historical.HistoricalCalendar:
	return {
		ConversionCalendar.HIJRI: historical.HistoricalCalendar.HIJRI_IIC,
		ConversionCalendar.GREGORIAN: historical.HistoricalCalendar.GREGORIAN,
		ConversionCalendar.JULIAN: historical.HistoricalCalendar.JULIAN,
	}[calendar]


def _date(calendar: ConversionCalendar, value) -> ConversionDate:
	return ConversionDate(calendar, value.year, value.month, value.day)


class HistoricalConversionService:
	def __init__(self, ummalqura: UmmAlQuraPort | None = None):
		self._ummalqura = ummalqura

	def convert(self, source: ConversionCalendar, target: ConversionCalendar, *,
			year: int, month: int, day: int,
			hijri_method: HijriMethod | None = None) -> ConversionResult:
		request = ConversionRequest(source, target, year, month, day, hijri_method)
		original = None
		rd = None
		reference = None
		source_bounds = target_bounds = None
		method = None
		stage = "request"

		def failure(code, field, bounds=None):
			return ConversionResult(request, original, None, method, rd, reference,
				source_bounds, target_bounds, ConversionError(code, field, stage, bounds))

		for field, value in (("source", source), ("target", target)):
			if not isinstance(value, ConversionCalendar):
				return failure("unsupported_calendar", field)
		if hijri_method is not None and not isinstance(hijri_method, HijriMethod):
			return failure("unsupported_hijri_method", "hijri_method")
		has_hijri = ConversionCalendar.HIJRI in (source, target)
		if has_hijri and hijri_method is None:
			return failure("hijri_method_required", "hijri_method")
		if not has_hijri and hijri_method is not None:
			return failure("unexpected_hijri_method", "hijri_method")
		method = hijri_method
		for field, value in (("year", year), ("month", month), ("day", day)):
			if type(value) is not int:
				return failure("invalid_type", field)
		for field, valid in (("year", year > 0), ("month", 1 <= month <= 12), ("day", day > 0)):
			if not valid:
				return failure("invalid_" + field, field)

		uses_ummalqura = method is HijriMethod.UMM_AL_QURA
		provider = self._ummalqura
		if uses_ummalqura and provider is None:
			return failure("ummalqura_provider_required", "provider")
		try:
			stage = "reference"
			if uses_ummalqura:
				metadata = provider.metadata
				source_info = metadata["source"]
				reference = UmmAlQuraReference(provider.hijri_data_version,
					str(metadata["tableFileSha256"]), str(source_info["project"]),
					str(source_info["release"]), str(source_info["url"]))
			elif method is HijriMethod.IIC:
				reference = historical.METHOD

			def bounds(calendar):
				if uses_ummalqura and calendar is ConversionCalendar.HIJRI:
					first = provider.first_supported_gregorian_date
					last = provider.last_supported_gregorian_date
					return ConversionBounds(first.toordinal(), last.toordinal(),
						_date(calendar, provider.from_gregorian(first)),
						_date(calendar, provider.from_gregorian(last)))
				identity = _historical_id(calendar)
				return ConversionBounds(historical.MIN_RD, historical.MAX_RD,
					_date(calendar, historical.from_rd(historical.MIN_RD, identity)),
					_date(calendar, historical.from_rd(historical.MAX_RD, identity)))

			source_bounds = bounds(source)
			target_bounds = bounds(target)
			stage = "source"
			if uses_ummalqura and source is ConversionCalendar.HIJRI:
				if not source_bounds.first.year <= year <= source_bounds.last.year:
					return failure("ummalqura_out_of_range", "year", source_bounds)
				if day > provider.month_length(year, month):
					return failure("invalid_day", "day")
				rd = provider.to_gregorian(CalendarDate(year, month, day,
					CalendarId.HIJRI_UMM_AL_QURA)).toordinal()
			else:
				rd = historical.to_rd(historical.HistoricalDate(_historical_id(source), year, month, day))
			original = ConversionDate(source, year, month, day)
			stage = "target"
			if not target_bounds.min_rd <= rd <= target_bounds.max_rd:
				code = "ummalqura_out_of_range" if uses_ummalqura and target is ConversionCalendar.HIJRI else "out_of_range"
				return failure(code, "date", target_bounds)
			if uses_ummalqura and target is ConversionCalendar.HIJRI:
				converted = _date(target, provider.from_gregorian(date.fromordinal(rd)))
			else:
				converted = _date(target, historical.from_rd(rd, _historical_id(target)))
			return ConversionResult(request, original, converted, method, rd, reference, source_bounds, target_bounds)
		except historical.HistoricalCalendarError as error:
			return failure(error.code.value, error.field,
				source_bounds if stage == "source" else target_bounds)
		except CalendarOutOfRangeError:
			return failure("ummalqura_out_of_range", "date",
				source_bounds if stage == "source" else target_bounds)
		except (OSError, RuntimeError, ValueError, TypeError, KeyError, AttributeError):
			# Provider failures never select another table or expose exception text.
			return failure("reference_data_error", "provider")
