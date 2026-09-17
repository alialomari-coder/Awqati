"""Behavioral regressions for bounded location lists and read-only draft previews."""
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
import ast
import sys
import threading
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "addon/globalPlugins"), str(ROOT / "tests")]
from awqati.domain import (default_settings, AnnouncementStyle, CalendarId, ClockType,
	DateFormat, Instant, Location, LocationKind, StoredLocation, TimeRepresentation)
from awqati.application.settings_preview import SettingsPreviewService, PreviewLocationRequired
from awqati.application import CalendarService, ClockService, PrayerService
from awqati.infrastructure import BundledLocationRepository, BundledTimezoneProvider, BundledCalculationMethodRepository
from awqati.nvda_adapter.preview import preview_text
from awqati.nvda_adapter.timezone_labels import TIMEZONE_LABELS
from test_calendar_service import providers
from support.event_clock import EventClock


class SettingsPreviewTests(unittest.TestCase):
	def setUp(self):
		self.settings = default_settings()
		self.settings.location = StoredLocation(LocationKind.SELECTED,
			Location("108410", "Riyadh", 24.6877, 46.7219, "Asia/Riyadh"), "SA")

	def test_all_calendars_formats_and_languages_leave_snapshot_unchanged(self):
		for language in ("ar", "en"):
			for identity in CalendarId:
				for style in DateFormat:
					self.settings.calendar.formats[identity] = style
					self.settings.calendar.hijri_adjustment_days = 2
					before = deepcopy(self.settings)
					self.assertTrue(preview_text(self.settings, "date", identity, language))
					self.assertEqual(self.settings, before)

	def test_both_clocks_all_styles_and_representations_are_previewable(self):
		for language in ("ar", "en"):
			for identity in ClockType:
				for style in AnnouncementStyle:
					for representation in TimeRepresentation:
						value = self.settings.clock.presentations[identity]
						value.style, value.representation = style, representation
						value.speak_seconds, value.speak_zero_minute = True, True
						before = deepcopy(self.settings)
						self.assertTrue(preview_text(self.settings, "clock", identity, language))
						self.assertEqual(self.settings, before)

	def test_missing_location_civil_single_and_date_work_but_ghurubi_needs_location(self):
		self.settings.location = None
		self.settings.clock.presentations[ClockType.ZAWALI].style = AnnouncementStyle.FULL
		self.assertTrue(preview_text(self.settings, "clock", ClockType.ZAWALI, "en"))
		self.assertTrue(preview_text(self.settings, "date", CalendarId.GREGORIAN, "en"))
		with self.assertRaises(PreviewLocationRequired):
			preview_text(self.settings, "clock", ClockType.GHURUBI, "ar")
		self.settings.clock.presentations[ClockType.ZAWALI].style = AnnouncementStyle.DOUBLE
		with self.assertRaises(PreviewLocationRequired):
			preview_text(self.settings, "clock", ClockType.ZAWALI, "ar")

	def test_civil_single_preview_never_requires_maghrib_calculation(self):
		clock = Mock()
		clock.read_civil.return_value = datetime(2026,9,15,12,30,tzinfo=timezone.utc)
		clock.read.side_effect = AssertionError("Civil time must not calculate Maghrib")
		self.settings.clock.presentations[ClockType.ZAWALI].style = AnnouncementStyle.FULL
		service = SettingsPreviewService(clock,None,None)
		self.assertIn("12 and 30 minutes",service.clock_text(self.settings,ClockType.ZAWALI,"en"))
		clock.read_civil.assert_called_once_with(self.settings.location.location)
		clock.read.assert_not_called()

	def test_selected_calendar_correction_changes_only_draft_output(self):
		now = EventClock(Instant(datetime(2026, 9, 12, 12, tzinfo=timezone.utc)))
		calendars = CalendarService(now, BundledTimezoneProvider(), providers())
		service = SettingsPreviewService(None, calendars, now)
		identity = CalendarId.HIJRI_UMM_AL_QURA
		self.settings.calendar.formats[identity] = DateFormat.FULL
		initial = service.date_text(self.settings, identity, "en")
		draft = deepcopy(self.settings);draft.calendar.hijri_adjustment_days = 1
		self.assertNotEqual(service.date_text(draft, identity, "en"), initial)
		self.assertEqual(service.date_text(self.settings, identity, "en"), initial)


class LocationBrowseTests(unittest.TestCase):
	def test_empty_query_browse_is_bounded_country_local_ranked_and_deterministic(self):
		repository = BundledLocationRepository()
		self.assertEqual(repository.loaded_country_codes, ())
		matches = repository.browse("SA", 40)
		self.assertEqual(len(matches), 40)
		self.assertEqual(repository.loaded_country_codes, ("SA",))
		self.assertEqual(matches[0].location.location_id, "108410")
		self.assertTrue(all(match.country_code == "SA" for match in matches))
		self.assertEqual(repository.browse("SA", 5), matches[:5])
		self.assertEqual(repository.search("SA", ""), ())
		self.assertFalse(repository.spatial_index_loaded)
		with self.assertRaises(ValueError):repository.browse("SA", 0)

	def test_timezone_display_mapping_retains_every_bundled_identity(self):
		ids = BundledTimezoneProvider().timezone_ids()
		self.assertEqual(set(ids), set(TIMEZONE_LABELS))
		for identity in ("Asia/Riyadh", "Europe/London", "America/New_York", "Africa/Asmara"):
			self.assertNotEqual(TIMEZONE_LABELS[identity], identity)
			self.assertEqual(ids[ids.index(identity)], identity)


class LocationSearchRaceTests(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		# Run the actual controller methods without replacing their race logic.
		tree = ast.parse((ROOT / "addon/globalPlugins/awqati/nvda_adapter/ui.py").read_text(encoding="utf-8"))
		node = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "LocationControls")
		namespace = {"threading":threading, "wx":SimpleNamespace(Window=object, Sizer=object,
			CommandEvent=object, NOT_FOUND=-1, CallAfter=lambda fn,*args:fn(*args)),
			"LocationSetupService":object, "StoredLocation":StoredLocation,
			"LocationSelectionResult":object, "LocationKind":LocationKind,
			"_":lambda text:text, "_location_summary":lambda stored:repr(stored), "TIMEZONE_LABELS":{},
			"location_choices":__import__("awqati.nvda_adapter.location_labels",fromlist=["location_choices"]).location_choices}
		exec(compile(ast.Module(body=[node],type_ignores=[]), "location-controller", "exec"), namespace)
		cls.controller = namespace["LocationControls"]

	def controller_instance(self):
		c = self.controller.__new__(self.controller)
		c._search_lock=threading.Lock();c._search_generation=2;c.parent=True
		c.matches=("current",);c._replace_items=Mock();c.service=Mock();c.language="ar"
		c.service.countries.return_value=(SimpleNamespace(code="SA",city_count=183),)
		return c

	def test_stale_completion_and_closed_window_cannot_replace_results(self):
		c=self.controller_instance();c._finish_search(1, ())
		self.assertEqual(c.matches,("current",));c._replace_items.assert_not_called()
		c.parent=False;c._finish_search(2, ())
		self.assertEqual(c.matches,("current",))

	def test_superseded_queued_worker_skips_io_and_empty_query_uses_browse(self):
		c=self.controller_instance();c._search_worker("SA", "old", 1)
		c.service.search.assert_not_called();c.service.browse.assert_not_called()
		c.service.browse.return_value=();c.city=object();c._search_worker("SA", "", 2)
		c.service.browse.assert_called_once_with("SA",c.service.countries()[0].city_count)
		self.assertEqual(c.matches,())

	def test_native_arrow_text_does_not_become_full_label_search(self):
		c=self.controller_instance();c._updating=False;c.city=Mock();c._search=Mock()
		c.city.GetSelection.return_value=-1;c.city.GetValue.return_value="بريدة — القصيم — آسيا / الرياض"
		c.city.GetStrings.return_value=["بريدة — القصيم — آسيا / الرياض"]
		c._on_search(Mock());c._search.assert_not_called()
		c.city.GetValue.return_value="بري";c._on_search(Mock());c._search.assert_called_once()

	def test_native_country_arrow_text_does_not_filter_the_list(self):
		c=self.controller_instance();c._updating=False;c.country=Mock();c._clear_city=Mock()
		c.country.GetSelection.return_value=-1;c.country.GetValue.return_value="السعودية"
		c.country.GetStrings.return_value=["السعودية","سوريا"]
		c._on_country_text(Mock());c._replace_items.assert_not_called();c._clear_city.assert_not_called()

	def test_country_change_clears_previous_pending_and_invalidates_results(self):
		c=self.controller_instance();c.pending=object();c.city=Mock();c.summary=Mock()
		c._clear_city()
		self.assertIsNone(c.pending);self.assertEqual(c.matches,());self.assertEqual(c._search_generation,3)
		c.city.ChangeValue.assert_called_once_with("")

	def test_custom_location_display_clears_previous_country_city_results(self):
		c=self.controller_instance();c.country=Mock();c.city=Mock();c.summary=Mock()
		c.countries=(SimpleNamespace(code="SA",name="Saudi Arabia"),)
		custom=StoredLocation(LocationKind.CUSTOM,Location("custom:1","My place",24.7,46.7,"Asia/Riyadh"))
		c._set_pending_display(custom)
		self.assertIsNone(c._country_code);self.assertEqual(c.matches,())
		c.city.SetItems.assert_called_once_with([])
		c.city.ChangeValue.assert_called_once_with("My place")

	def test_detection_busy_state_prevents_second_worker(self):
		c=self.controller_instance();c._detecting=True
		event=Mock()
		with unittest.mock.patch.object(threading,"Thread",side_effect=AssertionError("duplicate worker")):
			c._on_detect(event)

	def test_confirmation_no_and_yes_preserve_or_replace_only_pending(self):
		c=self.controller_instance();c.detect_button=Mock();c._set_pending_display=Mock()
		c.countries=(SimpleNamespace(code="SA",name="Saudi Arabia"),)
		previous=object();result=SimpleNamespace(location=StoredLocation(LocationKind.SELECTED,
			Location("108410","Riyadh",24.7,46.7,"Asia/Riyadh"),"SA"))
		wx=c._finish_detection.__globals__["wx"]
		for key in ("YES_NO","NO_DEFAULT","ICON_QUESTION","OK","ICON_WARNING"):setattr(wx,key,0)
		wx.YES=6
		for answer in (7,6):
			c.pending=previous;c._detecting=True;wx.MessageBox=Mock(return_value=answer)
			c._finish_detection(result)
			self.assertIs(c.pending, previous if answer==7 else result.location)
			self.assertFalse(c._detecting)
			c.detect_button.SetFocus.assert_called()
		c._set_pending_display.assert_called_once_with(result.location)


if __name__ == "__main__":unittest.main()
