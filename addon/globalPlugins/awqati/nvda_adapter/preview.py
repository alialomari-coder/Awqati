"""Compose existing services for an explicit settings preview on a worker thread."""
from ..application import CalendarService, ClockService, PrayerService
from ..application.settings_preview import SettingsPreviewService
from ..domain import (
	AfghanSolarHijriProvider, GregorianProvider, PersianSolarHijriProvider,
	SaudiSolarHijriProvider, PrayerCalculationRequest, PrayerCorrections, PrayerEventName, PrayerName,
)
from ..infrastructure import BundledCalculationMethodRepository, BundledTimezoneProvider, SystemNowProvider, UmmAlQuraProvider


def preview_text(settings, kind, identity, language):
	now = SystemNowProvider()
	zones = BundledTimezoneProvider()
	lunar = UmmAlQuraProvider()
	prayers = PrayerService(BundledCalculationMethodRepository(), zones, lunar_calendar=lunar)
	def request(day, location):
		config = settings.prayer
		return PrayerCalculationRequest(day, location.latitude, location.longitude, location.timezone_id,
			config.calculation_method, config.asr_method, config.high_latitude_rule,
			country_code=settings.location.country_code, corrections=PrayerCorrections(**{
				name.value: config.corrections_minutes[PrayerEventName(name.value)] for name in PrayerName}))
	clock = ClockService(now, zones, prayers, request)
	calendars = CalendarService(now, zones, (GregorianProvider(), lunar, SaudiSolarHijriProvider(),
		AfghanSolarHijriProvider(), PersianSolarHijriProvider()))
	service = SettingsPreviewService(clock, calendars, now)
	return service.clock_text(settings, identity, language) if kind == "clock" else service.date_text(settings, identity, language)
