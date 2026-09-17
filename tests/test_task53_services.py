from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from pathlib import Path
from types import SimpleNamespace
import unittest

from addon.globalPlugins.awqati.application import (
	CancellationToken, DataUpdateError, DataUpdateService, DiagnosticsService,
	DiagnosticsSnapshot, OnlinePrayerRequest, OnlinePrayerVerificationError,
	OnlinePrayerVerifier, OperationCancelled, UpdateChannelUnavailable,
)
from addon.globalPlugins.awqati.domain import (
	AsrMethod, CalculationMethod, HighLatitudeRule, PrayerName,
)


def manifest(data_type="locations", version="new", schema=2, payload=b"payload"):
	return {
		"schemaVersion": 1,
		"packages": [{
			"dataType": data_type, "dataVersion": version, "schemaVersion": schema,
			"sha256": hashlib.sha256(payload).hexdigest(),
			"url": "https://updates.example.invalid/package.zip",
		}],
	}


class Transport:
	def __init__(self, document, payload=b"payload", error=None):
		self.document, self.payload, self.error = document, payload, error
		self.calls = []

	def read_json(self, url, *, timeout, cancellation):
		self.calls.append(("manifest", url))
		if self.error:
			raise self.error
		return self.document

	def read_bytes(self, url, *, timeout, cancellation):
		self.calls.append(("package", url))
		if self.error:
			raise self.error
		return self.payload


class Installer:
	def __init__(self, error=None):
		self.error, self.installed = error, []

	def install(self, package, payload, cancellation):
		if self.error:
			raise self.error
		self.installed.append((package, payload))


class DataUpdateServiceTests(unittest.TestCase):
	def test_absent_or_non_https_channel_never_connects(self):
		for url in (None, "http://example.invalid/manifest.json"):
			transport = Transport(manifest())
			with self.assertRaises(UpdateChannelUnavailable):
				DataUpdateService(url, transport, Installer(), {}).check()
			self.assertEqual(transport.calls, [])

	def test_valid_manifest_sha_and_success(self):
		transport, installer = Transport(manifest()), Installer()
		result = DataUpdateService("https://example.invalid/manifest.json", transport, installer, {}).check()
		self.assertEqual(result.updated, ("locations",))
		self.assertEqual(len(installer.installed), 1)

	def test_current_version_is_unchanged_without_package_download(self):
		transport = Transport(manifest(version="same"))
		result = DataUpdateService("https://example.invalid/manifest.json", transport, Installer(),
			{"locations": "same"}).check()
		self.assertEqual(result.unchanged, ("locations",))
		self.assertEqual([item[0] for item in transport.calls], ["manifest"])

	def test_invalid_manifest_schema_and_package_schema(self):
		for document in (
			{"schemaVersion": 2, "packages": []},
			manifest(schema=99),
			{"schemaVersion": 1, "packages": "bad"},
		):
			with self.assertRaises(DataUpdateError):
				DataUpdateService("https://example.invalid/m", Transport(document), Installer(), {}).check()

	def test_bad_sha_or_corrupt_package_does_not_report_success(self):
		document = manifest()
		document["packages"][0]["sha256"] = "0" * 64
		with self.assertRaisesRegex(DataUpdateError, "SHA-256"):
			DataUpdateService("https://example.invalid/m", Transport(document), Installer(), {}).check()
		with self.assertRaisesRegex(DataUpdateError, "corrupt"):
			DataUpdateService("https://example.invalid/m", Transport(manifest()),
				Installer(DataUpdateError("corrupt data")), {}).check()

	def test_network_timeout_preserves_installer(self):
		installer = Installer()
		with self.assertRaises(DataUpdateError):
			DataUpdateService("https://example.invalid/m",
				Transport(manifest(), error=TimeoutError("timed out")), installer, {}).check()
		self.assertEqual(installer.installed, [])

	def test_cancelled_before_request(self):
		token, transport = CancellationToken(), Transport(manifest())
		token.cancel()
		with self.assertRaises(OperationCancelled):
			DataUpdateService("https://example.invalid/m", transport, Installer(), {}).check(cancellation=token)
		self.assertEqual(transport.calls, [])

	def test_only_five_packages_are_accepted(self):
		approved = {
			"locations": 2, "timezones": 1, "ummalqura": 1,
			"calculationMethods": 1, "arabianCalendar": 1,
		}
		for data_type, schema in approved.items():
			DataUpdateService._parse_manifest(manifest(data_type=data_type, schema=schema))
		for data_type in ("saudiSolarHijri", "persianSolarHijri", "afghanSolarHijri", "other"):
			with self.assertRaises(DataUpdateError):
				DataUpdateService._parse_manifest(manifest(data_type=data_type))


class Provider:
	def __init__(self, values=None, error=None):
		self.values, self.error, self.calls = values, error, 0

	def fetch(self, request, *, timeout, cancellation):
		self.calls += 1
		if self.error:
			raise self.error
		return self.values


def internal_times():
	values = {}
	for index, prayer in enumerate(PrayerName):
		values[prayer.value] = datetime(2026, 9, 17, 5 + index * 2, 0, tzinfo=timezone.utc)
	return SimpleNamespace(**values)


def online_values(offset=0):
	return {prayer: (5 + index * 2) * 60 + offset for index, prayer in enumerate(PrayerName)}


class OnlinePrayerVerifierTests(unittest.TestCase):
	def setUp(self):
		self.request = OnlinePrayerRequest(
			__import__("datetime").date(2026, 9, 17), 24.7, 46.7,
			CalculationMethod.MAKKAH, AsrMethod.STANDARD, HighLatitudeRule.AUTO,
		)

	def test_six_times_only_and_two_minute_tolerance(self):
		self.assertTrue(OnlinePrayerVerifier(Provider(online_values(2))).verify(
			self.request, internal_times()).is_close)
		result = OnlinePrayerVerifier(Provider(online_values(3))).verify(self.request, internal_times())
		self.assertEqual(len(result.differences), 6)
		self.assertTrue(all(value.difference_minutes == 3 for value in result.differences))

	def test_missing_malformed_timeout_and_service_failure(self):
		for values, error in (
			({PrayerName.FAJR: 300}, None),
			({**online_values(), PrayerName.FAJR: "05:00"}, None),
			(None, TimeoutError("timeout")),
			(None, RuntimeError("service failed")),
		):
			with self.assertRaises(OnlinePrayerVerificationError):
				OnlinePrayerVerifier(Provider(values, error)).verify(self.request, internal_times())

	def test_cancellation_prevents_provider_call(self):
		token, provider = CancellationToken(), Provider(online_values())
		token.cancel()
		with self.assertRaises(OperationCancelled):
			OnlinePrayerVerifier(provider).verify(self.request, internal_times(), cancellation=token)
		self.assertEqual(provider.calls, 0)

	def test_internal_objects_are_not_mutated(self):
		internal, provider = internal_times(), Provider(online_values(9))
		before = tuple(getattr(internal, prayer.value) for prayer in PrayerName)
		OnlinePrayerVerifier(provider).verify(self.request, internal)
		self.assertEqual(before, tuple(getattr(internal, prayer.value) for prayer in PrayerName))


class DiagnosticsServiceTests(unittest.TestCase):
	def test_required_fields_are_present_and_private_fields_cannot_be_supplied(self):
		snapshot = DiagnosticsSnapshot(
			"0.5.3.1", "2026.2", "3.13", "Windows 11", 1,
			"locations-v1", "tz-v1", "hijri-v1", "methods-v1", "arabian-v1",
			"Asia/Riyadh", "108410", "MAKKAH", "AUTO", "active", "enabled",
		)
		report = DiagnosticsService().create_report(snapshot)
		for value in ("0.5.3.1", "2026.2", "3.13", "Windows 11", "locations-v1",
				"tz-v1", "hijri-v1", "methods-v1", "arabian-v1", "Asia/Riyadh",
				"108410", "MAKKAH", "AUTO", "active", "enabled"):
			self.assertIn(value, report)
		for forbidden in ("24.7000", "46.7000", "daily wird", "sound path", "configpath"):
			self.assertNotIn(forbidden, report.lower())
