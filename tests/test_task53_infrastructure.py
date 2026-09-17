from __future__ import annotations

from datetime import date
from io import BytesIO
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from addon.globalPlugins.awqati.application import (
	CancellationToken, DataPackageManifest, DataUpdateError, OnlinePrayerRequest, OperationCancelled,
)
from addon.globalPlugins.awqati.domain import AsrMethod, CalculationMethod, HighLatitudeRule, PrayerName
from addon.globalPlugins.awqati.infrastructure import AlAdhanPrayerProvider, AtomicDataPackageInstaller
from addon.globalPlugins.awqati.infrastructure.network_services import HttpsTransport


ROOT = Path(__file__).resolve().parents[1]


def calculation_package() -> bytes:
	source = ROOT / "addon/globalPlugins/awqati/data/calculation_methods"
	stream = BytesIO()
	with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
		for name in ("methods.json", "country_methods.json", "NOTICE.txt"):
			archive.write(source / name, name)
	return stream.getvalue()


class AtomicInstallerTests(unittest.TestCase):
	def package(self, payload):
		return DataPackageManifest(
			"calculationMethods", "awqati-4.0-methods-1", 1,
			hashlib.sha256(payload).hexdigest(), "https://example.invalid/package.zip",
		)

	def test_valid_package_is_installed_and_invalid_package_preserves_current(self):
		with tempfile.TemporaryDirectory() as temporary:
			root = Path(temporary)
			installer, payload = AtomicDataPackageInstaller(root), calculation_package()
			installer.install(self.package(payload), payload, CancellationToken())
			current = root / "data/calculationMethods/current"
			self.assertTrue((current / "methods.json").is_file())
			before = (current / "methods.json").read_bytes()
			with self.assertRaises(DataUpdateError):
				installer.install(self.package(b"not a zip"), b"not a zip", CancellationToken())
			self.assertEqual((current / "methods.json").read_bytes(), before)

	def test_replace_failure_rolls_back_previous_package(self):
		with tempfile.TemporaryDirectory() as temporary:
			root = Path(temporary)
			installer, payload = AtomicDataPackageInstaller(root), calculation_package()
			installer.install(self.package(payload), payload, CancellationToken())
			current = root / "data/calculationMethods/current"
			marker = current / "marker.txt"
			marker.write_text("previous", encoding="utf-8")
			original = Path.replace
			failed = [False]

			def replace(path, target):
				if path.name == "payload" and not failed[0]:
					failed[0] = True
					raise OSError("simulated replace failure")
				return original(path, target)

			with patch.object(Path, "replace", replace):
				with self.assertRaises(DataUpdateError):
					installer.install(self.package(payload), payload, CancellationToken())
			self.assertEqual(marker.read_text(encoding="utf-8"), "previous")

	def test_unsafe_archive_is_rejected(self):
		stream = BytesIO()
		with zipfile.ZipFile(stream, "w") as archive:
			archive.writestr("../escape", "bad")
		with tempfile.TemporaryDirectory() as temporary:
			with self.assertRaises(DataUpdateError):
				AtomicDataPackageInstaller(Path(temporary)).install(
					DataPackageManifest("calculationMethods", "x", 1,
						hashlib.sha256(stream.getvalue()).hexdigest(), "https://example.invalid/x"),
					stream.getvalue(), CancellationToken())


class AlAdhanProviderTests(unittest.TestCase):
	def request(self):
		return OnlinePrayerRequest(
			date(2026, 9, 17), 24.7, 46.7, CalculationMethod.MAKKAH,
			AsrMethod.HANAFI, HighLatitudeRule.ONE_SEVENTH,
		)

	def test_parses_exactly_six_times_and_sends_approved_parameters(self):
		document = {"code": 200, "data": {"timings": {
			"Fajr": "04:30 (+03)", "Sunrise": "05:50", "Dhuhr": "11:50",
			"Asr": "15:20", "Maghrib": "17:55", "Isha": "19:25",
			"Midnight": "23:00", "Lastthird": "02:00",
		}}}
		seen = {}

		def read(instance, url, *, timeout, cancellation):
			seen["url"] = url
			return json.dumps(document).encode()

		with patch.object(HttpsTransport, "read_bytes", read):
			result = AlAdhanPrayerProvider().fetch(
				self.request(), timeout=2, cancellation=CancellationToken())
		self.assertEqual(set(result), set(PrayerName))
		self.assertIn("method=4", seen["url"])
		self.assertIn("school=1", seen["url"])
		self.assertIn("latitudeAdjustmentMethod=2", seen["url"])
		self.assertNotIn("Midnight", seen["url"])

	def test_missing_or_malformed_json_is_rejected(self):
		for payload in (b"not json", json.dumps({"code": 200, "data": {"timings": {"Fajr": "04:00"}}}).encode()):
			with self.subTest(payload=payload[:10]), patch.object(HttpsTransport, "read_bytes", return_value=payload):
				with self.assertRaises(Exception):
					AlAdhanPrayerProvider().fetch(
						self.request(), timeout=2, cancellation=CancellationToken())

	def test_cancellation_from_https_is_preserved(self):
		with patch.object(HttpsTransport, "read_bytes", side_effect=OperationCancelled("cancelled")):
			with self.assertRaises(OperationCancelled):
				AlAdhanPrayerProvider().fetch(
					self.request(), timeout=2, cancellation=CancellationToken())
