"""Explicit, read-only previews of a settings snapshot; no scheduler or persistence."""
from dataclasses import replace
from ..domain import AnnouncementStyle, ClockFormatOptions, ClockType, TimeRepresentation
from .clock_formatters import ArabicWordClockFormatter, EnglishWordClockFormatter, NumericClockFormatter
from .calendar_formatters import ArabicDateFormatter, EnglishDateFormatter


class PreviewLocationRequired(ValueError):
	pass


def clock_formatter(language, representation):
	if representation is TimeRepresentation.WORDS:
		if language == "ar":
			return ArabicWordClockFormatter()
		if language == "en":
			return EnglishWordClockFormatter()
	return NumericClockFormatter(language)


def clock_options(value):
	return ClockFormatOptions(value.hour_system, value.speak_seconds, value.speak_zero_minute, value.style)


class SettingsPreviewService:
	def __init__(self, clock, calendars, now):
		self.clock, self.calendars, self.now = clock, calendars, now

	def clock_text(self, settings, identity, language):
		presentations = settings.clock.presentations
		value = presentations[identity]
		options = clock_options(value)
		formatter = clock_formatter(language, value.representation)
		location = settings.location.location if settings.location else None
		if identity is ClockType.ZAWALI and value.style is not AnnouncementStyle.DOUBLE:
			return formatter.format_civil_announcement(self.clock.read_civil(location), options)
		if location is None:
			raise PreviewLocationRequired()
		reading = self.clock.read(location)
		if value.style is AnnouncementStyle.DOUBLE:
			# Double always announces civil time followed by Ghurubi time; each
			# component uses its own draft representation, hours and seconds.
			zawali, ghurubi = (presentations[k] for k in ClockType)
			return clock_formatter(language, zawali.representation).format_announcement(
				reading, ClockType.ZAWALI, replace(clock_options(zawali), style=AnnouncementStyle.DOUBLE),
				ghurubi_formatter=clock_formatter(language, ghurubi.representation),
				ghurubi_options=clock_options(ghurubi))
		return formatter.format_announcement(reading, identity, options)

	def date_text(self, settings, identity, language):
		options = settings.calendar
		if settings.location:
			reading = self.calendars.read(settings.location.location, identity,
				hijri_adjustment=options.hijri_adjustment_days)
		else:
			reading = self.calendars.read_date(self.now.now().value.astimezone().date(), identity,
				hijri_adjustment=options.hijri_adjustment_days)
		formatter = ArabicDateFormatter() if language == "ar" else EnglishDateFormatter()
		return formatter.format_calendar(reading, options.formats[identity])
