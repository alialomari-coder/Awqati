from __future__ import annotations

import json
import hashlib
from datetime import date, timedelta
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ROOT / "addon" / "globalPlugins"
if str(PACKAGES) not in sys.path:
	sys.path.insert(0, str(PACKAGES))

from awqati.application import ArabianCalendarService  # noqa: E402
from awqati.domain import SuhailCycleType  # noqa: E402
from awqati.infrastructure import ARABIAN_CALENDAR_DATA_VERSION, BundledArabianCalendarRepository  # noqa: E402


SOURCE = ROOT / "data_sources" / "Awqati_ArabianCalendar_Data_v1"
RUNTIME = ROOT / "addon" / "globalPlugins" / "awqati" / "data" / "arabian_calendar"


class ArabianCalendarDataTests(unittest.TestCase):
	@classmethod
	def setUpClass(cls) -> None:
		cls.repository = BundledArabianCalendarRepository()
		cls.service = ArabianCalendarService(cls.repository)
		cls.rich = json.loads((RUNTIME / "arabian_calendar.json").read_text(encoding="utf-8"))
		cls.common = json.loads((RUNTIME / "arabian_calendar_days_common.json").read_text(encoding="utf-8"))
		cls.leap = json.loads((RUNTIME / "arabian_calendar_days_leap.json").read_text(encoding="utf-8"))

	def test_version_counts_and_source_manifest_provenance(self) -> None:
		self.assertEqual(ARABIAN_CALENDAR_DATA_VERSION, "2026.09.16-r2")
		self.assertEqual(self.repository.arabian_calendar_data_version, ARABIAN_CALENDAR_DATA_VERSION)
		self.assertEqual(self.rich["schemaVersion"], 1)
		self.assertEqual(self.rich["arabianCalendarDataVersion"], ARABIAN_CALENDAR_DATA_VERSION)
		self.assertEqual(len(self.rich["talaa"]), 28)
		self.assertEqual((len(self.common["orderedDateKeys"]), len(self.common["daysByDate"])), (365, 365))
		self.assertEqual((len(self.leap["orderedDateKeys"]), len(self.leap["daysByDate"])), (366, 366))
		self.assertEqual(len(set(self.common["orderedDateKeys"])), 365)
		self.assertEqual(len(set(self.leap["orderedDateKeys"])), 366)
		manifest = json.loads((SOURCE / "manifest.json").read_text(encoding="utf-8"))
		for file_entry in manifest["files"]:
			payload = (SOURCE / file_entry["name"]).read_bytes()
			self.assertEqual(len(payload), file_entry["sizeBytes"])
			self.assertEqual(hashlib.sha256(payload).hexdigest(), file_entry["sha256"])
		entry = next(item for item in manifest["files"] if item["name"] == "arabian_calendar.json")
		self.assertEqual(entry["sizeBytes"], 71049)
		self.assertEqual(entry["sha256"], "de783557d1dc1fa7f094a957f4a33fb1d602b5f7c7e9b226233f4a4b67baf7dd")

	def test_complete_common_and_leap_cycles_have_no_gaps(self) -> None:
		for anchor, length, cycle_type in (
			(date(2023, 8, 24), 366, SuhailCycleType.LEAP),
			(date(2024, 8, 24), 365, SuhailCycleType.COMMON),
		):
			readings = [self.service.read_date(anchor + timedelta(days=offset)) for offset in range(length)]
			self.assertEqual([value.suhail_day for value in readings], list(range(1, length + 1)))
			self.assertTrue(all(value.cycle_type is cycle_type for value in readings))
			self.assertEqual(readings[-1].local_date, date(anchor.year + 1, 8, 23))
			self.assertEqual(readings[-1].days_remaining, 0)

	def test_all_28_talaa_transitions_match_the_daily_indexes(self) -> None:
		for index in (self.common, self.leap):
			ids = [index["daysByDate"][key]["talaaId"] for key in index["orderedDateKeys"]]
			transitions = [ids[0], *(ids[position] for position in range(1, len(ids)) if ids[position] != ids[position - 1])]
			self.assertEqual(len(transitions), 28)
			self.assertEqual(transitions, [item["id"] for item in sorted(self.rich["talaa"], key=lambda value: value["order"])])

	def test_suhail_boundaries_and_special_talaa_lengths(self) -> None:
		self.assertEqual(self.service.read_date(date(2024, 8, 23)).suhail_day, 366)
		self.assertEqual(self.service.read_date(date(2024, 8, 24)).suhail_day, 1)
		for sample in (date(2023, 9, 6), date(2024, 9, 6)):
			value = self.service.read_date(sample)
			self.assertEqual((value.talaa.id, value.talaa_length), ("jabhah", 14))
		self.assertEqual(self.service.read_date(date(2023, 2, 23)).talaa_length, 13)
		self.assertEqual(self.service.read_date(date(2024, 2, 23)).talaa_length, 14)
		leap_day = self.service.read_date(date(2024, 2, 29))
		self.assertEqual((leap_day.talaa.id, leap_day.talaa_day, leap_day.talaa_length), ("saad_bula", 7, 14))
		self.assertEqual((self.service.read_date(date(2024, 2, 28)).suhail_day,
			self.service.read_date(date(2024, 2, 28)).talaa_day), (189, 6))
		self.assertEqual((self.service.read_date(date(2024, 3, 1)).suhail_day,
			self.service.read_date(date(2024, 3, 1)).talaa_day), (191, 8))
		self.assertEqual((self.service.read_date(date(2024, 3, 7)).suhail_day,
			self.service.read_date(date(2024, 3, 7)).talaa_day), (197, 14))
		for sample in (date(2023, 3, 8), date(2024, 3, 8)):
			self.assertEqual(self.service.read_date(sample).talaa.id, "saad_al_suud")
		self.assertEqual(self.service.read_date(date(2023, 3, 8)).suhail_day, 197)
		self.assertEqual(self.service.read_date(date(2024, 3, 8)).suhail_day, 198)

	def test_all_season_boundaries(self) -> None:
		for season in self.rich["seasons"]:
			month, day = season["start"]["month"], season["start"]["day"]
			year = 2024 if month >= 8 else 2025
			start = date(year, month, day)
			self.assertEqual(self.service.read_date(start).season.id, season["id"])
			self.assertNotEqual(self.service.read_date(start - timedelta(days=1)).season.id, season["id"])
			end_month, end_day = season["end"]["month"], season["end"]["day"]
			end_year = year if (end_month, end_day) >= (month, day) else year + 1
			end = date(end_year, end_month, end_day)
			self.assertEqual(self.service.read_date(end).season.id, season["id"])
			if (end.month, end.day) != (8, 23):
				self.assertNotEqual(self.service.read_date(end + timedelta(days=1)).season.id, season["id"])

	def test_supported_overlap_period_boundaries(self) -> None:
		for period_id, start, end in (
			("kinna_al_thurayya", date(2025, 4, 29), date(2025, 6, 6)),
			("murabba_al_qayz", date(2025, 6, 7), date(2025, 7, 15)),
		):
			self.assertNotIn(period_id, {value.id for value in self.service.read_date(start - timedelta(days=1)).overlapping_periods})
			self.assertIn(period_id, {value.id for value in self.service.read_date(start).overlapping_periods})
			self.assertIn(period_id, {value.id for value in self.service.read_date(end).overlapping_periods})
			self.assertNotIn(period_id, {value.id for value in self.service.read_date(end + timedelta(days=1)).overlapping_periods})

	def test_every_season_and_overlap_start_event_occurs_only_on_its_first_day(self) -> None:
		for season in self.rich["seasons"]:
			month, day = season["start"]["month"], season["start"]["day"]
			year = 2024 if month >= 8 else 2025
			start = date(year, month, day)
			current = self.service.read_date(start)
			next_day = self.service.read_date(start + timedelta(days=1))
			self.assertTrue(any(event.type in {"year_and_season_start", "season_start"} for event in current.start_events))
			self.assertFalse(any(event.type in {"year_and_season_start", "season_start"} for event in next_day.start_events))
		for start in (date(2025, 4, 29), date(2025, 6, 7)):
			self.assertTrue(any(event.type == "overlap_start" for event in self.service.read_date(start).start_events))
			self.assertFalse(any(event.type == "overlap_start" for event in self.service.read_date(start + timedelta(days=1)).start_events))

	def test_sayings_are_sequential_complete_and_not_repeated(self) -> None:
		for index in (self.common, self.leap):
			by_talaa: dict[str, list[str]] = {}
			for key in index["orderedDateKeys"]:
				item = index["daysByDate"][key]
				if item.get("shortSayingId"):
					by_talaa.setdefault(item["talaaId"], []).append(item["shortSayingId"])
			for talaa in self.rich["talaa"]:
				self.assertEqual(by_talaa.get(talaa["id"], []), [value["id"] for value in talaa["sayings"]])
		self.assertEqual(self.service.read_date(date(2024, 2, 23)).short_saying.id, "saad_bula_saying_01")
		self.assertIsNone(self.service.read_date(date(2024, 2, 24)).short_saying)
		self.assertIsNone(self.service.read_date(date(2024, 2, 27)).short_saying)
		texts = {s["text"] for t in self.rich["talaa"] for s in t["sayings"]}
		self.assertIn("«إذا طلع المرزم يا خراف الزم.»", texts)
		self.assertNotIn("«إذا طلع المرزم يملأ الحزم.»", texts)

	def test_cache_parses_bundle_once(self) -> None:
		repository = BundledArabianCalendarRepository()
		repository.read(date(2024, 2, 27))
		repository.read(date(2025, 8, 24))
		self.assertEqual(repository.load_count, 1)


if __name__ == "__main__":
	unittest.main()
