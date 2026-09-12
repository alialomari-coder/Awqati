from __future__ import annotations

from datetime import datetime, timedelta, timezone
import importlib
from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ROOT / "addon" / "globalPlugins"
if str(PACKAGES) not in sys.path:
	sys.path.insert(0, str(PACKAGES))

from awqati.infrastructure.tzif_timezone import TzifTimezone  # noqa: E402


class TzifFallbackTests(unittest.TestCase):
	def test_bundled_tzif_parser_handles_reference_dst_and_fromutc(self) -> None:
		root = ROOT / "addon/globalPlugins/awqati/data/timezones/zoneinfo"
		expected = {"Asia/Riyadh": (3, 3), "Europe/London": (0, 1),
			"Europe/Oslo": (1, 2), "America/New_York": (-5, -4)}
		for key, offsets in expected.items():
			zone = TzifTimezone.from_bytes((root / Path(*key.split("/"))).read_bytes(), key)
			winter = datetime(2026, 1, 15, 12, tzinfo=zone)
			summer = datetime(2026, 7, 15, 12, tzinfo=zone)
			with self.subTest(key=key):
				self.assertEqual((winter.utcoffset(), summer.utcoffset()),
					(tuple(timedelta(hours=value) for value in offsets)))
				utc = datetime(2026, 7, 15, 12, tzinfo=timezone.utc)
				self.assertEqual(utc.astimezone(zone).utcoffset(), summer.utcoffset())

	def test_every_bundled_zone_parses_for_winter_and_summer_without_zoneinfo(self) -> None:
		root = ROOT / "addon/globalPlugins/awqati/data/timezones"
		import json
		metadata = json.loads((root / "metadata.json").read_text(encoding="utf-8"))
		for key in metadata["zones"]:
			zone = TzifTimezone.from_bytes((root / "zoneinfo" / Path(*key.split("/"))).read_bytes(), key)
			with self.subTest(key=key):
				self.assertIsNotNone(datetime(2026, 1, 15, 12, tzinfo=zone).utcoffset())
				self.assertIsNotNone(datetime(2026, 7, 15, 12, tzinfo=zone).utcoffset())

	def test_provider_import_and_real_calculation_path_work_when_zoneinfo_is_missing(self) -> None:
		module_name = "awqati.infrastructure.timezone_provider"
		saved = sys.modules.pop(module_name, None)
		real_import = __import__
		def blocked(name, *args, **kwargs):
			if name == "zoneinfo":
				raise ImportError("simulated trimmed NVDA runtime")
			return real_import(name, *args, **kwargs)
		try:
			with mock.patch("builtins.__import__", side_effect=blocked):
				module = importlib.import_module(module_name)
				zone = module.BundledTimezoneProvider().get_timezone("Europe/London")
			self.assertIsInstance(zone, TzifTimezone)
			self.assertEqual(datetime(2026, 7, 15, 12, tzinfo=zone).utcoffset(), timedelta(hours=1))
		finally:
			sys.modules.pop(module_name, None)
			if saved is not None:
				sys.modules[module_name] = saved


if __name__ == "__main__":
	unittest.main()
