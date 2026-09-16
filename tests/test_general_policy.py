from __future__ import annotations

from datetime import datetime, time, timezone
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ROOT / "addon" / "globalPlugins"
if str(PACKAGES) not in sys.path:
	sys.path.insert(0, str(PACKAGES))

from awqati.application import (  # noqa: E402
	AutomaticAlertKind,
	LOCATION_REQUIRED_MESSAGE,
	automatic_alert_policy,
	first_run_location_required,
	is_quiet_time,
	location_requirement_message,
	manual_commands_allowed,
)
from awqati.domain import ClockTime, Instant, Location, QuietHoursSettings, SettingsApplied, default_settings  # noqa: E402


class GeneralPolicyTests(unittest.TestCase):
	def test_first_run_and_location_guard_have_no_fallback(self) -> None:
		settings = default_settings()
		self.assertTrue(first_run_location_required(settings))
		self.assertEqual(location_requirement_message(None), LOCATION_REQUIRED_MESSAGE)
		self.assertEqual(
			LOCATION_REQUIRED_MESSAGE,
			"No location has been assigned. Set it in Awqati settings, then try again.",
		)
		location = Location("1", "Riyadh", 24.7, 46.6, "Asia/Riyadh")
		settings.location = __import__("awqati.domain", fromlist=["StoredLocation"]).StoredLocation(
			__import__("awqati.domain", fromlist=["LocationKind"]).LocationKind.SELECTED, location, "SA")
		self.assertFalse(first_run_location_required(settings))
		self.assertIsNone(location_requirement_message(location))
		self.assertTrue(manual_commands_allowed())

	def test_quiet_hours_use_start_inclusive_end_exclusive_boundaries(self) -> None:
		quiet = QuietHoursSettings(True, ClockTime(13, 0), ClockTime(15, 0))
		for value, expected in ((time(12, 59), False), (time(13), True), (time(14, 59), True), (time(15), False)):
			with self.subTest(value=value):
				self.assertEqual(is_quiet_time(value, quiet), expected)

	def test_quiet_hours_cross_midnight_and_disabled_or_equal_are_inactive(self) -> None:
		quiet = QuietHoursSettings(True, ClockTime(22, 0), ClockTime(6, 0))
		for value, expected in ((time(21, 59), False), (time(22), True), (time(23, 59), True), (time(0), True), (time(5, 59), True), (time(6), False)):
			with self.subTest(value=value):
				self.assertEqual(is_quiet_time(value, quiet), expected)
		quiet.enabled = False
		self.assertFalse(is_quiet_time(time(23), quiet))
		quiet.enabled = True
		quiet.end = ClockTime(22, 0)
		self.assertFalse(is_quiet_time(time(23), quiet))

	def test_global_switch_and_quiet_hours_do_not_mutate_child_settings(self) -> None:
		settings = default_settings()
		original = (settings.prayer.alerts_enabled, settings.clock.automatic_alert_enabled, settings.adhkar.alerts_enabled)
		settings.general.all_automatic_alerts_enabled = False
		decision = automatic_alert_policy(settings, AutomaticAlertKind.OTHER, time(12))
		self.assertFalse(decision.deliver)
		self.assertTrue(decision.suppressed_by_global_switch)
		self.assertEqual(original, (settings.prayer.alerts_enabled, settings.clock.automatic_alert_enabled, settings.adhkar.alerts_enabled))

	def test_prayer_alerts_are_exempt_from_quiet_hours_until_explicitly_enabled(self) -> None:
		settings = default_settings()
		settings.general.quiet_hours.enabled = True
		inside = time(23)
		self.assertFalse(automatic_alert_policy(settings, AutomaticAlertKind.OTHER, inside).deliver)
		self.assertTrue(automatic_alert_policy(settings, AutomaticAlertKind.PRAYER, inside).deliver)
		settings.general.quiet_hours.apply_to_prayer_alerts = True
		decision = automatic_alert_policy(settings, AutomaticAlertKind.PRAYER, inside)
		self.assertFalse(decision.deliver)
		self.assertTrue(decision.suppressed_by_quiet_hours)

	def test_settings_applied_rebuild_marker_is_an_instant_not_a_catch_up_range(self) -> None:
		now = Instant(datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc))
		event = SettingsApplied(now, 1, now)
		self.assertEqual(event.automatic_alerts_rebuild_from, now)
		self.assertFalse(hasattr(event, "catch_up_from"))


if __name__ == "__main__":
	unittest.main()
