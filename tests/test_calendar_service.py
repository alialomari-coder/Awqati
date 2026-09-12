from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ROOT / "addon" / "globalPlugins"
if str(PACKAGES) not in sys.path:
	sys.path.insert(0, str(PACKAGES))
if str(ROOT / "tests") not in sys.path:
	sys.path.insert(0, str(ROOT / "tests"))

from awqati.application import CalendarService  # noqa: E402
from awqati.domain import (  # noqa: E402
	AfghanSolarHijriProvider, CalendarId, GregorianProvider, Instant,
	InvalidHijriAdjustmentError, Location, PersianSolarHijriProvider,
	SaudiSolarHijriProvider, UnsupportedCalendarError,
)
from awqati.infrastructure import UmmAlQuraProvider  # noqa: E402
from support.event_clock import EventClock  # noqa: E402


class FixedTimezoneProvider:
	def __init__(self, zones):
		self.zones = zones

	def get_timezone(self, timezone_id):
		return self.zones[timezone_id]


class FailingProvider(PersianSolarHijriProvider):
	def from_gregorian(self, value):
		raise RuntimeError("pinned provider failure")


def providers():
	return (GregorianProvider(), UmmAlQuraProvider(), SaudiSolarHijriProvider(),
		PersianSolarHijriProvider(), AfghanSolarHijriProvider())


class CalendarServiceTests(unittest.TestCase):
	def setUp(self) -> None:
		self.clock = EventClock(Instant(datetime(2026, 9, 12, 12, tzinfo=timezone.utc)))
		self.zone = timezone(timedelta(hours=3))
		self.location = Location("riyadh", "Riyadh", 24.7, 46.7, "Asia/Riyadh")
		self.service = CalendarService(self.clock,
			FixedTimezoneProvider({"Asia/Riyadh": self.zone}), providers())

	def test_explicit_identity_selects_exact_provider_and_never_falls_back(self) -> None:
		for calendar_id, provider_type in (
			(CalendarId.GREGORIAN, GregorianProvider),
			(CalendarId.HIJRI_UMM_AL_QURA, UmmAlQuraProvider),
			(CalendarId.SAUDI_SOLAR_HIJRI, SaudiSolarHijriProvider),
			(CalendarId.PERSIAN_SOLAR_HIJRI, PersianSolarHijriProvider),
			(CalendarId.AFGHAN_SOLAR_HIJRI, AfghanSolarHijriProvider),
		):
			self.assertIsInstance(self.service.provider(calendar_id), provider_type)
		with self.assertRaises(UnsupportedCalendarError):
			self.service.provider("ar")  # type: ignore[arg-type]
		missing = CalendarService(self.clock, FixedTimezoneProvider({"Asia/Riyadh": self.zone}),
			(GregorianProvider(), UmmAlQuraProvider()))
		with self.assertRaises(UnsupportedCalendarError):
			missing.read(self.location, CalendarId.PERSIAN_SOLAR_HIJRI)
		failing = CalendarService(self.clock, FixedTimezoneProvider({"Asia/Riyadh": self.zone}),
			(GregorianProvider(), UmmAlQuraProvider(), SaudiSolarHijriProvider(),
				FailingProvider(), AfghanSolarHijriProvider()))
		with self.assertRaisesRegex(RuntimeError, "pinned provider failure"):
			failing.read(self.location, CalendarId.PERSIAN_SOLAR_HIJRI)

	def test_adjustment_is_applied_once_and_preserves_civil_solar_and_weekday(self) -> None:
		baseline = self.service.read_date(date(2026, 9, 12), CalendarId.SAUDI_SOLAR_HIJRI)
		for correction, expected in ((-2, (1448, 3, 28)), (-1, (1448, 3, 29)),
				(0, (1448, 4, 1)), (1, (1448, 4, 2)), (2, (1448, 4, 3))):
			reading = self.service.read_date(date(2026, 9, 12),
				CalendarId.SAUDI_SOLAR_HIJRI, hijri_adjustment=correction)
			self.assertEqual((reading.lunar_visible.year, reading.lunar_visible.month,
				reading.lunar_visible.day), expected)
			self.assertEqual(reading.lunar_base, baseline.lunar_base)
			self.assertEqual(reading.gregorian, baseline.gregorian)
			self.assertEqual(reading.selected, baseline.selected)
			self.assertEqual(reading.weekday, baseline.weekday)
		for invalid in (-3, 3):
			with self.assertRaises(InvalidHijriAdjustmentError):
				self.service.read_date(date(2026, 9, 12), CalendarId.GREGORIAN,
					hijri_adjustment=invalid)
		with self.assertRaises(TypeError):
			self.service.read_date(date(2026, 9, 12), CalendarId.GREGORIAN,
				hijri_adjustment=True)  # type: ignore[arg-type]

	def test_all_non_lunar_calendars_ignore_visible_lunar_correction(self) -> None:
		for calendar_id in (CalendarId.GREGORIAN, CalendarId.SAUDI_SOLAR_HIJRI,
				CalendarId.PERSIAN_SOLAR_HIJRI, CalendarId.AFGHAN_SOLAR_HIJRI):
			minus = self.service.read_date(date(2026, 9, 12), calendar_id, hijri_adjustment=-2)
			plus = self.service.read_date(date(2026, 9, 12), calendar_id, hijri_adjustment=2)
			self.assertEqual(minus.selected, plus.selected)
			self.assertEqual(minus.weekday, plus.weekday)

	def test_local_day_changes_at_midnight_not_at_utc_or_maghrib(self) -> None:
		instants = (
			(datetime(2026, 9, 12, 20, 59, 59, tzinfo=timezone.utc), date(2026, 9, 12)),
			(datetime(2026, 9, 12, 21, 0, 0, tzinfo=timezone.utc), date(2026, 9, 13)),
			(datetime(2026, 9, 12, 21, 0, 1, tzinfo=timezone.utc), date(2026, 9, 13)),
		)
		for instant, expected in instants:
			self.clock.set(Instant(instant))
			reading = self.service.read(self.location, CalendarId.HIJRI_UMM_AL_QURA)
			self.assertEqual(reading.civil_date, expected)
			self.assertEqual(reading.weekday, expected.weekday())
		self.clock.set(Instant(datetime(2026, 9, 12, 15, 0, tzinfo=timezone.utc)))
		before_evening = self.service.read(self.location, CalendarId.HIJRI_UMM_AL_QURA)
		self.clock.set(Instant(datetime(2026, 9, 12, 18, 30, tzinfo=timezone.utc)))
		after_evening = self.service.read(self.location, CalendarId.HIJRI_UMM_AL_QURA)
		self.assertEqual(before_evening.selected, after_evening.selected)

	def test_utc_date_change_does_not_override_local_date(self) -> None:
		west = timezone(timedelta(hours=-4))
		location = Location("dst-sample", "Sample", 40.0, -74.0, "America/Test")
		service = CalendarService(self.clock, FixedTimezoneProvider({"America/Test": west}), providers())
		self.clock.set(Instant(datetime(2026, 7, 2, 1, 0, tzinfo=timezone.utc)))
		self.assertEqual(service.read(location, CalendarId.GREGORIAN).civil_date, date(2026, 7, 1))


if __name__ == "__main__":
	unittest.main()
