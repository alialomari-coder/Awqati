"""Dedicated gettext domain: new converter strings do not alter NVDA's catalog."""
import gettext
from pathlib import Path

from ..application.calendar_formatters import ArabicDateFormatter, EnglishDateFormatter, _SYRIAC_MONTHS
from ..application.historical_conversion import ConversionCalendar as C, HijriMethod
from ..domain.calendar import CalendarId


class ConverterText:
	def __init__(self, language):
		self.arabic = language.replace("_", "-").lower().split("-")[0] == "ar"
		self.gettext = gettext.translation("calendar_converter",
			localedir=Path(__file__).resolve().parents[3] / "locale",
			languages=["ar" if self.arabic else "en"], fallback=True).gettext
		self.months = (ArabicDateFormatter if self.arabic else EnglishDateFormatter).months

	def month(self, source, number):
		identity = CalendarId.HIJRI_UMM_AL_QURA if source is C.HIJRI else CalendarId.GREGORIAN
		return self.months[identity][number - 1] if 1 <= number <= 12 else ""

	def date(self, value):
		era = self.calendar(value.calendar)
		return f"{value.day} {self.month(value.calendar, value.month)} {value.year} ({era})"

	def calendar(self, calendar):
		return self.gettext({C.HIJRI: "Hijri", C.GREGORIAN: "Gregorian", C.JULIAN: "Julian"}[calendar])

	def clipboard_date(self, value):
		"""Copy only the converted date, in the owner's approved language format."""
		month = self.month(value.calendar, value.month)
		if self.arabic:
			if value.calendar is C.HIJRI:
				return f"{value.day} {month} {value.year} هـ"
			text = f"{value.day} {month} {_SYRIAC_MONTHS[value.month - 1]} {value.year} م"
			return text + (" (يولياني)" if value.calendar is C.JULIAN else "")
		if value.calendar is C.HIJRI:
			return f"{value.day} {month} {value.year} AH"
		return f"{value.day} {month} {value.year} CE ({self.calendar(value.calendar)})"

	def result(self, result):
		_ = self.gettext
		if result.hijri_method is HijriMethod.UMM_AL_QURA:
			reference = _("Reference: Umm al-Qura.")
		elif result.hijri_method is HijriMethod.IIC:
			reference = _("Reference: historical calculation IIc.")
		else:
			reference = _("Reference: Gregorian–Julian conversion.")
		return _("Original date: {date}").format(date=self.date(result.original)) + "\n" + \
			_("Converted date: {date}").format(date=self.date(result.converted)) + "\n" + \
			reference

	def error(self, error):
		_ = self.gettext
		return {
			"invalid_number": _("Enter a whole positive number using English, Arabic or Persian digits, without spaces or separators."),
			"invalid_day": _("The day is not valid for the selected month and year."),
			"invalid_month": _("Enter a month from 1 to 12."),
			"invalid_year": _("Enter a year greater than zero."),
			"ummalqura_out_of_range": _("This date is outside the Umm al-Qura range. You can use advanced conversion for historical dates."),
			"out_of_range": _("The year or date is outside the supported range."),
			"date_context_required": _("Enter a valid month and year before changing the day with navigation keys."),
			"ummalqura_provider_required": _("Umm al-Qura data is unavailable. Close the converter and check the active data."),
			"reference_data_error": _("The calendar reference is unavailable or invalid. No alternative reference was used."),
		}.get(error.code, _("The date could not be converted. Check the input and the calendar data."))
