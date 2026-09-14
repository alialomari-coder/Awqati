from __future__ import annotations

import ast
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ROOT / "addon" / "globalPlugins"
sys.path.insert(0, str(PACKAGES))

from awqati.application import SettingsDraft  # noqa: E402
from awqati.domain import (  # noqa: E402
	AlertAction, AnnouncementStyle, CalendarId, ClockType, DateFormat, DayPeriod,
	EveningReference, FridayReference, MorningReference, PrayerEventName,
	RecurringDhikrId, default_settings,
)
from awqati.nvda_adapter.settings_sections import (  # noqa: E402
	CALENDAR_EDIT_ORDER, PRIMARY_CALENDAR_ORDER, PRAYER_ACTIONS, PRAYER_EVENT_ORDER,
	RECURRING_ACTIONS, RECURRING_DHIKR_ORDER, SECTION_ORDER, STANDARD_ALERT_ACTIONS,
	SettingsSection, action_uses_sound, hijri_adjustment_visible,
)


class Task33SettingsContractTests(unittest.TestCase):
	def setUp(self) -> None:
		self.settings = default_settings()

	def test_sections_are_ordered_and_prayer_is_always_first(self) -> None:
		self.assertEqual(SECTION_ORDER, (
			SettingsSection.PRAYER, SettingsSection.CLOCK,
			SettingsSection.DATE, SettingsSection.ADHKAR,
		))
		self.assertFalse(hasattr(self.settings, "selected_section"))

	def test_prayer_events_are_ordered_and_independent(self) -> None:
		self.assertEqual(PRAYER_EVENT_ORDER, (
			PrayerEventName.FAJR, PrayerEventName.SUNRISE, PrayerEventName.DHUHR,
			PrayerEventName.ASR, PrayerEventName.MAGHRIB, PrayerEventName.ISHA,
			PrayerEventName.MIDNIGHT, PrayerEventName.LAST_THIRD,
		))
		self.settings.prayer.events[PrayerEventName.FAJR].pre_alert_minutes = 17
		self.assertEqual(self.settings.prayer.events[PrayerEventName.DHUHR].pre_alert_minutes, 10)

	def test_iqama_and_post_alert_shapes_match_event_kind(self) -> None:
		for name in PRAYER_EVENT_ORDER:
			event = self.settings.prayer.events[name]
			if name in {PrayerEventName.FAJR, PrayerEventName.DHUHR, PrayerEventName.ASR,
					PrayerEventName.MAGHRIB, PrayerEventName.ISHA}:
				self.assertIsNotNone(event.iqama)
				self.assertIsNone(event.post_alert)
			else:
				self.assertIsNone(event.iqama)
				self.assertIsNotNone(event.post_alert)

	def test_prayer_defaults_and_bounds_are_exposed_by_schema(self) -> None:
		self.assertTrue(self.settings.prayer.alerts_enabled)
		self.assertEqual([self.settings.prayer.events[name].iqama.delay_minutes for name in (
			PrayerEventName.FAJR, PrayerEventName.DHUHR, PrayerEventName.ASR,
			PrayerEventName.MAGHRIB, PrayerEventName.ISHA)], [25, 20, 20, 10, 20])
		self.assertEqual(self.settings.prayer.current_prayer_after_iqama_minutes, 20)
		self.assertEqual([self.settings.prayer.events[name].post_alert_minutes for name in (
			PrayerEventName.SUNRISE, PrayerEventName.MIDNIGHT, PrayerEventName.LAST_THIRD)], [20, 0, 0])

	def test_clock_roles_presentations_intervals_and_actions(self) -> None:
		self.assertEqual(tuple(ClockType), (ClockType.ZAWALI, ClockType.GHURUBI))
		self.assertFalse(self.settings.clock.automatic_alert_enabled)
		self.assertTrue(self.settings.clock.intervals.on_hour)
		self.assertEqual(STANDARD_ALERT_ACTIONS,
			(AlertAction.SPEECH, AlertAction.SOUND, AlertAction.SOUND_AND_SPEECH))
		self.settings.clock.presentations[ClockType.ZAWALI].style = AnnouncementStyle.SHORT
		self.assertIs(self.settings.clock.presentations[ClockType.GHURUBI].style, AnnouncementStyle.DOUBLE)

	def test_calendar_edit_and_primary_lists_are_distinct(self) -> None:
		self.assertEqual(CALENDAR_EDIT_ORDER, (
			CalendarId.HIJRI_UMM_AL_QURA, CalendarId.GREGORIAN,
			CalendarId.SAUDI_SOLAR_HIJRI, CalendarId.AFGHAN_SOLAR_HIJRI,
			CalendarId.PERSIAN_SOLAR_HIJRI,
		))
		self.assertEqual(PRIMARY_CALENDAR_ORDER,
			(CalendarId.HIJRI_UMM_AL_QURA, CalendarId.GREGORIAN))

	def test_hijri_correction_visibility_rule(self) -> None:
		for calendar_id in CALENDAR_EDIT_ORDER:
			self.assertTrue(hijri_adjustment_visible(calendar_id, DateFormat.DOUBLE))
		for date_format in (DateFormat.FULL, DateFormat.MODERATE, DateFormat.SHORT):
			self.assertTrue(hijri_adjustment_visible(CalendarId.HIJRI_UMM_AL_QURA, date_format))
			for calendar_id in CALENDAR_EDIT_ORDER[1:]:
				self.assertFalse(hijri_adjustment_visible(calendar_id, date_format))

	def test_adhkar_defaults_and_action_sets(self) -> None:
		adhkar = self.settings.adhkar
		self.assertTrue(adhkar.alerts_enabled)
		self.assertEqual((adhkar.morning.enabled, adhkar.evening.enabled,
			adhkar.friday_hour.enabled, adhkar.daily_wird.enabled, adhkar.recurring.enabled),
			(False, False, False, False, False))
		self.assertEqual((adhkar.morning.reference, adhkar.morning.minutes),
			(MorningReference.BEFORE_SUNRISE, 15))
		self.assertEqual((adhkar.evening.reference, adhkar.evening.minutes),
			(EveningReference.BEFORE_MAGHRIB, 15))
		self.assertEqual((adhkar.friday_hour.reference, adhkar.friday_hour.minutes),
			(FridayReference.BEFORE_MAGHRIB, 60))
		self.assertEqual((adhkar.daily_wird.hour, adhkar.daily_wird.minute, adhkar.daily_wird.period),
			(10, 0, DayPeriod.PM))
		self.assertEqual(adhkar.recurring.interval_minutes, 60)
		self.assertEqual(RECURRING_ACTIONS, (AlertAction.SPEECH, AlertAction.SOUND))

	def test_recurring_items_are_complete_enabled_and_independent(self) -> None:
		self.assertEqual(RECURRING_DHIKR_ORDER, tuple(RecurringDhikrId))
		items = self.settings.adhkar.recurring.items
		self.assertTrue(all(item.enabled for item in items.values()))
		items[RecurringDhikrId.SUBHAN_ALLAH].enabled = False
		self.assertTrue(items[RecurringDhikrId.ALHAMDU_LILLAH].enabled)

	def test_sound_visibility_depends_only_on_neutral_action(self) -> None:
		self.assertFalse(action_uses_sound(AlertAction.SILENT))
		self.assertFalse(action_uses_sound(AlertAction.SPEECH))
		self.assertTrue(action_uses_sound(AlertAction.SOUND))
		self.assertTrue(action_uses_sound(AlertAction.SOUND_AND_SPEECH))
		self.assertEqual(PRAYER_ACTIONS, tuple(AlertAction))

	def test_draft_keeps_unsaved_edits_across_all_selector_identities(self) -> None:
		draft = SettingsDraft(self.settings)
		draft.settings.prayer.events[PrayerEventName.FAJR].pre_alert_minutes = 12
		draft.settings.clock.presentations[ClockType.GHURUBI].speak_seconds = True
		draft.settings.calendar.formats[CalendarId.PERSIAN_SOLAR_HIJRI] = DateFormat.SHORT
		draft.settings.adhkar.recurring.items[RecurringDhikrId.ALLAHU_AKBAR].enabled = False
		self.assertEqual(draft.settings.prayer.events[PrayerEventName.FAJR].pre_alert_minutes, 12)
		self.assertTrue(draft.settings.clock.presentations[ClockType.GHURUBI].speak_seconds)
		self.assertIs(draft.settings.calendar.formats[CalendarId.PERSIAN_SOLAR_HIJRI], DateFormat.SHORT)
		self.assertFalse(draft.settings.adhkar.recurring.items[RecurringDhikrId.ALLAHU_AKBAR].enabled)
		self.assertEqual(self.settings.prayer.events[PrayerEventName.FAJR].pre_alert_minutes, 10)


class Task33ArchitectureTests(unittest.TestCase):
	def test_dynamic_panels_are_destroyed_and_selector_focus_is_restored(self) -> None:
		source = (PACKAGES / "awqati" / "nvda_adapter" / "settings_panel.py").read_text(encoding="utf-8-sig")
		self.assertIn("self._section_panel.Destroy()", source)
		self.assertIn("self.section_choice.SetFocus()", source)
		self.assertIn("self._prayer_event_panel.Destroy()", source)
		self.assertIn("old.Destroy()", source)

	def test_panel_uses_draft_and_does_not_store_selector_or_write_json(self) -> None:
		source = (PACKAGES / "awqati" / "nvda_adapter" / "settings_panel.py").read_text(encoding="utf-8-sig")
		self.assertIn("open_draft()", source)
		self.assertIn("self._settings.apply(self._draft)", source)
		for forbidden in ("selectedSection", "selected_section", "json.dump", "Scheduler", "requests", "urllib", "socket"):
			self.assertNotIn(forbidden, source)

	def test_wav_selection_is_asynchronous_and_transactional(self) -> None:
		source = (PACKAGES / "awqati" / "nvda_adapter" / "settings_panel.py").read_text(encoding="utf-8-sig")
		self.assertIn("threading.Thread", source)
		self.assertIn("wx.CallAfter", source)
		self.assertIn("wx.adv.Sound", source)
		self.assertIn("self._sound_staging.begin_commit", source)
		self.assertIn("self._sound_staging.rollback", source)
		self.assertIn("def onDiscard", source)
		self.assertNotIn("read_bytes()", source)
		self.assertNotIn("shutil.copy2", source)
		tree = ast.parse(source)
		choose = next(node for node in ast.walk(tree)
			if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "_on_choose")
		self.assertTrue(any(isinstance(node, ast.Assign)
			and any(isinstance(target, ast.Name) and target.id == "source" for target in node.targets)
			for node in choose.body[3].body))

	def test_domain_remains_free_of_wx_and_nvda(self) -> None:
		for path in (PACKAGES / "awqati" / "domain").glob("*.py"):
			tree = ast.parse(path.read_text(encoding="utf-8"))
			imports = {alias.name.split(".")[0] for node in ast.walk(tree)
				if isinstance(node, ast.Import) for alias in node.names}
			self.assertTrue(imports.isdisjoint({"wx", "gui", "globalPluginHandler"}), path.name)

	def test_plugin_registers_the_task33_panel(self) -> None:
		source = (PACKAGES / "awqati" / "nvda_adapter" / "plugin.py").read_text(encoding="utf-8")
		self.assertIn("from .settings_panel import AwqatiSettingsPanel", source)


if __name__ == "__main__":
	unittest.main()
