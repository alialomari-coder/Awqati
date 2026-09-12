from __future__ import annotations

from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path
import socket
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_PACKAGES = ROOT / "addon" / "globalPlugins"
if str(PLUGIN_PACKAGES) not in sys.path:
	sys.path.insert(0, str(PLUGIN_PACKAGES))

from awqati.application import TimezoneProvider  # noqa: E402
from awqati.domain import Location  # noqa: E402
from awqati.infrastructure import (  # noqa: E402
	BundledTimezoneProvider,
	TimezoneDataError,
	UnknownTimezoneError,
)


class BundledTimezoneProviderTests(unittest.TestCase):
	def test_reference_offsets_and_dst_use_bundled_tzif(self) -> None:
		provider = BundledTimezoneProvider()
		self.assertIsInstance(provider, TimezoneProvider)
		self.assertEqual(provider.tz_data_version, "2026.3")
		expected = {
			"Asia/Riyadh": (3, 3),
			"Europe/London": (0, 1),
			"Europe/Oslo": (1, 2),
			"America/New_York": (-5, -4),
			"America/Toronto": (-5, -4),
			"Europe/Istanbul": (3, 3),
			"Asia/Jakarta": (7, 7),
			"Asia/Kuala_Lumpur": (8, 8),
		}
		for key, (winter, summer) in expected.items():
			zone = provider.get_timezone(key)
			with self.subTest(key=key):
				self.assertEqual(datetime(2026, 1, 15, 12, tzinfo=zone).utcoffset(), timedelta(hours=winter))
				self.assertEqual(datetime(2026, 7, 15, 12, tzinfo=zone).utcoffset(), timedelta(hours=summer))

	def test_unknown_unsafe_and_corrupt_zones_have_controlled_errors(self) -> None:
		provider = BundledTimezoneProvider()
		for key in ("Missing/Zone", "../UTC", "/UTC", "Europe\\London", ""):
			with self.subTest(key=key), self.assertRaises(UnknownTimezoneError):
				provider.get_timezone(key)
		with tempfile.TemporaryDirectory() as temporary:
			root = Path(temporary)
			(root / "zoneinfo/Test").mkdir(parents=True)
			data = b"broken"
			(root / "zoneinfo/Test/Zone").write_bytes(data)
			metadata = {
				"schemaVersion": 1, "tzDataVersion": "fixture", "zoneCount": 1,
				"zones": {"Test/Zone": hashlib.sha256(data).hexdigest()},
			}
			(root / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
			with self.assertRaises(TimezoneDataError):
				BundledTimezoneProvider(root).get_timezone("Test/Zone")

	def test_custom_location_uses_iana_zone_without_repository_or_network(self) -> None:
		location = Location("custom-home", "Home", 24.5, 46.7, "Asia/Riyadh")
		with mock.patch.object(socket, "socket", side_effect=AssertionError("network attempted")):
			zone = BundledTimezoneProvider().get_timezone(location.timezone_id)
		self.assertEqual(datetime(2026, 1, 15, tzinfo=zone).utcoffset(), timedelta(hours=3))


if __name__ == "__main__":
	unittest.main()
