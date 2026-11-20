from copy import deepcopy
from datetime import datetime, timezone, timedelta
import io
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "addon/globalPlugins"))
from awqati.domain import default_settings, Location
from awqati.domain.weather import WeatherSettings, WeatherPeriod, WeatherSnapshot, CODES, description
from awqati.application.weather_formatters import WeatherFormatter, number, convert
from awqati.application.weather_service import WeatherService, CacheEntry
from awqati.infrastructure.weather_provider import (OpenMeteoProvider, WeatherError, parse_weather,
                                                    requested_fields, retry_seconds, MAX_BYTES)
from awqati.infrastructure.timezone_provider import BundledTimezoneProvider
from awqati.infrastructure.settings_repository import JsonSettingsRepository, _encode, InvalidSettingsDataError, SettingsWriteError

ZONES = BundledTimezoneProvider()
NOW = datetime(2026, 11, 20, 9, tzinfo=timezone.utc)
LOCATION = Location("fixture", "Riyadh", 24.7, 46.7, "Asia/Riyadh")


def fixture(now=NOW, zone=None):
    zone = zone or ZONES.get_timezone("Asia/Riyadh")
    local = now.astimezone(zone)
    current = {"time": int(now.timestamp()), "interval": 900, "weather_code": 2, "temperature_2m": 22,
               "apparent_temperature": 21, "wind_speed_10m": 3.4, "wind_direction_10m": 0,
               "relative_humidity_2m": 0, "wind_gusts_10m": 7, "precipitation": .001,
               "pressure_msl": 1015, "visibility": 10000, "cloud_cover": 0, "uv_index": 0}
    units = {"time": "unixtime", "interval": "seconds", "weather_code": "wmo code", "temperature_2m": "°C", "apparent_temperature": "°C", "wind_speed_10m": "m/s", "wind_direction_10m": "°", "relative_humidity_2m": "%", "wind_gusts_10m": "m/s", "precipitation": "mm", "pressure_msl": "hPa", "visibility": "m", "cloud_cover": "%", "uv_index": ""}
    daily = {"time": [int((local.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=i)).timestamp()) for i in range(7)],
             "weather_code": [2]*7, "temperature_2m_max": [26]*7, "temperature_2m_min": [17]*7,
             "precipitation_probability_max": [0]*7, "precipitation_sum": [0]*7,
             "wind_speed_10m_max": [4]*7, "wind_gusts_10m_max": [7]*7,
             "wind_direction_10m_dominant": [0]*7, "uv_index_max": [0]*7}
    daily_units = {"time": "unixtime", "weather_code": "wmo code", "temperature_2m_max": "°C", "temperature_2m_min": "°C", "precipitation_probability_max": "%", "precipitation_sum": "mm", "wind_speed_10m_max": "m/s", "wind_gusts_10m_max": "m/s", "wind_direction_10m_dominant": "°", "uv_index_max": ""}
    hourly = {"time": [int(now.replace(minute=0, second=0, microsecond=0).timestamp()) + 3600*i for i in range(1, 14)], "weather_code": [2]*13,
              "temperature_2m": [22]*13, "precipitation_probability": [0]*13, "wind_speed_10m": [3]*13}
    hourly_units = {k: units.get(k, "%") for k in hourly}
    return dict(current=current, current_units=units, daily=daily, daily_units=daily_units, hourly=hourly, hourly_units=hourly_units)


class Response(io.BytesIO):
    def __init__(self, data, headers=None):
        super().__init__(json.dumps(data).encode() if isinstance(data, dict) else data)
        self.headers = headers or {}
    def geturl(self): return "https://api.open-meteo.com/v1/forecast"


class ProviderTests(unittest.TestCase):
    def test_complete_zero_missing_invalid_and_units(self):
        data = fixture()
        parsed = parse_weather(data, ZONES.get_timezone(LOCATION.timezone_id))
        self.assertEqual(parsed.current.values["relative_humidity_2m"], 0)
        for value in (None, "22", True, float("nan"), float("inf"), -999):
            data["current"]["temperature_2m"] = value
            self.assertNotIn("temperature_2m", parse_weather(data, timezone.utc).current.values)
        data["current_units"]["wind_speed_10m"] = "km/h"
        self.assertNotIn("wind_speed_10m", parse_weather(data, timezone.utc).current.values)
        data["current_units"]["interval"] = "minutes"
        self.assertEqual(parse_weather(data, timezone.utc).current.interval, 0)

    def test_bad_roots_and_empty_core(self):
        for payload in (None, [], {}, {"current": "bad"}, {"current": {"time": 1}, "current_units": {}}):
            with self.subTest(payload=payload), self.assertRaises(WeatherError): parse_weather(payload, timezone.utc)

    def test_bad_lengths_and_dates(self):
        data = fixture()
        data["daily"]["temperature_2m_max"].pop()
        parsed = parse_weather(data, ZONES.get_timezone(LOCATION.timezone_id))
        self.assertNotIn("temperature_2m_max", parsed.daily[0].values)
        data["daily"]["time"] = [None] * 7
        self.assertFalse(parse_weather(data, timezone.utc).daily)

    def test_dst_daily_midnights_and_non_midnight_omission(self):
        zone = ZONES.get_timezone("America/New_York")
        for now in (datetime(2026, 3, 7, 15, tzinfo=timezone.utc), datetime(2026, 10, 31, 15, tzinfo=timezone.utc)):
            data = fixture(now, zone)
            parsed = parse_weather(data, zone)
            self.assertEqual(len(parsed.daily), 7)
            steps = [b - a for a, b in zip(data["daily"]["time"], data["daily"]["time"][1:])]
            self.assertTrue(82800 in steps or 90000 in steps)
            data["daily"]["time"][2] += 3600
            self.assertEqual(len(parse_weather(data, zone).daily), 5)

    def test_https_limits_timeout_bad_json(self):
        requests = []
        def opener(request, timeout):
            requests.append((request.full_url, timeout))
            return Response(fixture())
        provider = OpenMeteoProvider(ZONES, opener)
        provider.fetch(LOCATION, WeatherSettings())
        self.assertTrue(requests[0][0].startswith("https://"))
        self.assertIn("wind_speed_unit=ms", requests[0][0])
        self.assertNotIn("us_aqi", requests[0][0])
        self.assertEqual(requests[0][1], 10)
        for response in (b"broken", b"[]", b"x" * (MAX_BYTES + 1)):
            provider.opener = lambda *a, data=response, **k: Response(data)
            with self.assertRaises(WeatherError): provider.fetch(LOCATION, WeatherSettings())

    def test_http_retry_and_network_errors(self):
        provider = OpenMeteoProvider(ZONES)
        for error, kind in ((HTTPError("https://test", 429, "limited", {"Retry-After": "120"}, None), "rate"),
                            (HTTPError("https://test", 500, "server", {}, None), "server"),
                            (HTTPError("https://test", 400, "bad", {}, None), "request"), (URLError("offline"), "network"), (TimeoutError(), "network")):
            def fail(*a, **k): raise error
            provider.opener = fail
            with self.assertRaises(WeatherError) as result: provider.fetch(LOCATION, WeatherSettings())
            self.assertEqual(result.exception.kind, kind)
        self.assertEqual(retry_seconds("120"), 120)
        self.assertEqual(retry_seconds("Thu, 01 Jan 1970 00:02:00 GMT", now=0), 120)

    def test_fields_only_selected_and_unchanged_for_units(self):
        settings = WeatherSettings()
        first = requested_fields(settings)
        settings.unit_system = "imperial"
        self.assertEqual(first, requested_fields(settings))
        settings.current["pressure_msl"] = True
        self.assertIn("pressure_msl", requested_fields(settings)[0])
        self.assertNotIn("uv_index", first[0])

    def test_finite_corrupt_magnitudes_are_omitted_before_formatting(self):
        data = fixture()
        keys = ("wind_speed_10m", "wind_gusts_10m", "pressure_msl", "visibility", "precipitation", "uv_index")
        for key in keys: data["current"][key] = 1e308
        parsed = parse_weather(data, ZONES.get_timezone(LOCATION.timezone_id))
        self.assertFalse(set(keys) & parsed.current.values.keys())
        settings = WeatherSettings(detail="detailed")
        settings.current = dict.fromkeys(settings.current, True)
        self.assertIn("Open-Meteo", WeatherFormatter(settings, "en", timezone.utc, NOW).format(parsed, "current", "Fixture", copyable=True))


class FormatterTests(unittest.TestCase):
    def setUp(self):
        self.zone = ZONES.get_timezone(LOCATION.timezone_id)
        self.snapshot = parse_weather(fixture(), self.zone)
        self.settings = WeatherSettings()

    def fmt(self, lang="en", report="current", **kwargs):
        return WeatherFormatter(self.settings, lang, self.zone, NOW).format(self.snapshot, report, "Riyadh", **kwargs)

    def test_rounding_negative_zero_and_conversion(self):
        self.assertEqual(number(2.5), "3")
        self.assertEqual(number(-2.5), "-3")
        self.assertEqual(number(-.001, 1), "0")
        pairs = (("fahrenheit", 0, 32), ("kelvin", 0, 273.15), ("kmh", 10, 36), ("mph", .44704, 1), ("knots", 1852/3600, 1), ("mmhg", 1.33322387415, 1), ("inhg", 33.8638866667, 1), ("km", 1000, 1), ("miles", 1609.344, 1), ("inches", 25.4, 1))
        for unit, source, target in pairs: self.assertAlmostEqual(convert(source, unit), target)

    def test_known_unknown_codes(self):
        for code in CODES:
            self.assertNotIn("unknown", description(code))
            self.assertNotEqual(description(code), description(code, True))
        self.assertIn("unknown", description(999))

    def test_bilingual_brief_and_detailed_options_zero_and_tiny_rain(self):
        self.assertNotIn("humidity", self.fmt())
        self.settings.detail = "detailed"
        text = self.fmt()
        self.assertIn("humidity 0 percent", text)
        self.assertIn("wind gusts", text)
        self.assertNotIn("sea-level pressure", text)
        self.settings.current["precipitation"] = True
        self.assertIn("less than 0.1 millimetres", self.fmt())
        self.assertIn("أقل من 0.1 ملليمتر", self.fmt("ar"))
        self.assertNotIn("last update", self.fmt())

    def test_directions_calm_and_custom_kelvin(self):
        formatter = WeatherFormatter(self.settings, "en", self.zone, NOW)
        self.assertIn("from north", formatter.wind({"wind_speed_10m": 2, "wind_direction_10m": 0}))
        self.assertIn("from northeast", formatter.wind({"wind_speed_10m": 2, "wind_direction_10m": 22.5}))
        self.assertEqual(formatter.wind({"wind_speed_10m": .4, "wind_direction_10m": 180}), "calm wind")
        self.settings.unit_system = "custom"
        self.settings.custom_units["temperature"] = "kelvin"
        self.assertIn("295 kelvin", self.fmt())
        self.settings.detail = "detailed"
        self.assertIn("295.2 kelvin", self.fmt())

    def test_forecast_bounds_and_optional_fields_isolation(self):
        for count in range(2, 7):
            self.settings.future_days = count
            self.assertEqual(self.fmt(report="future").count("highest hourly"), count)
        self.settings.detail = "detailed"
        self.settings.today["precipitation_sum"] = False
        self.assertNotIn("expected daily precipitation amount", self.fmt(report="today"))
        self.assertIn("expected daily precipitation amount", self.fmt(report="future"))

    def test_hours_change_condensation_and_local_midnight(self):
        for hours in (3, 6, 12):
            self.settings.upcoming_hours = hours
            text = self.fmt(report="today")
            self.assertIn("No significant change", text)
        data = fixture()
        data["hourly"]["weather_code"][2:] = [61]*11
        self.snapshot = parse_weather(data, self.zone)
        self.assertIn("light rain", self.fmt(report="today"))
        self.settings.detail = "detailed"
        self.assertEqual(self.fmt(report="today").count("At "), 5)
        formatter = WeatherFormatter(self.settings, "en", self.zone, NOW.replace(hour=20))
        self.assertIn("tomorrow", formatter.time_label(NOW + timedelta(hours=13)))

    def test_copyable_source_air_and_no_station_claim(self):
        air = WeatherPeriod(NOW, {"us_aqi": 42})
        self.settings.current["us_aqi"] = True
        self.settings.detail = "detailed"
        text = self.fmt(air=air, copyable=True)
        for fragment in ("CAMS", "U.S. air quality index 42, good", "creativecommons.org", "not local station", "open-meteo.com"):
            self.assertIn(fragment, text)
        self.assertNotIn("CAMS", self.fmt(air=None))

    def test_dst_fold_times_are_distinct_and_normal_times_are_natural(self):
        zone = ZONES.get_timezone("America/New_York")
        formatter = WeatherFormatter(self.settings, "en", zone, datetime(2026, 11, 1, 4, tzinfo=timezone.utc))
        first = formatter.time_label(datetime(2026, 11, 1, 5, tzinfo=timezone.utc))
        second = formatter.time_label(datetime(2026, 11, 1, 6, tzinfo=timezone.utc))
        self.assertIn("1 AM", first)
        self.assertIn("minus 4 hours", first)
        self.assertIn("minus 5 hours", second)
        self.assertNotEqual(first, second)
        normal = WeatherFormatter(self.settings, "ar", self.zone, NOW).time_label(NOW)
        self.assertIn("ظهرًا", normal)
        self.assertNotIn("UTC", normal)

    def test_temperature_change_stays_relative_to_now_after_condition_change(self):
        data = fixture()
        data["hourly"]["temperature_2m"] = [26, 28, 28] + [28]*10
        data["hourly"]["weather_code"] = [0]*13
        snapshot = parse_weather(data, self.zone)
        self.settings.detail = "detailed"
        hourly = WeatherFormatter(self.settings, "en", self.zone, NOW).hourly(snapshot)
        self.assertEqual(hourly.count("At "), 4)
        self.assertIn("28 degrees Celsius", hourly)


class FakeProvider:
    zones = ZONES
    def fetch(self, location, settings): return parse_weather(fixture(), ZONES.get_timezone(location.timezone_id))
    def fetch_air(self, location): return WeatherPeriod(NOW, {"us_aqi": 42})


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.jobs, self.events = [], []
        self.tick = 0
        self.provider = FakeProvider()
        self.service = WeatherService(self.provider, lambda fn, *args: fn(*args),
            clock=lambda: self.tick, utcnow=lambda: NOW, launch=self.jobs.append)
        self.settings = WeatherSettings(enabled=True)
        self.service.configure(self.settings, LOCATION)

    def request(self, report="current", force=False):
        self.service.request(report, lambda *args: self.events.append(args), lambda: self.events.append("wait"), force)

    def finish(self):
        jobs, self.jobs[:] = list(self.jobs), []
        for job in jobs: job()

    def test_merge_wait_cache_and_latest_report_only(self):
        self.request()
        self.request("today")
        self.request("future")
        self.assertEqual(len(self.jobs), 1)
        self.assertEqual(self.events.count("wait"), 1)
        self.finish()
        self.assertEqual(len([e for e in self.events if isinstance(e, tuple)]), 1)
        self.events.clear()
        self.request()
        self.assertNotIn("wait", self.events)
        self.assertEqual(len(self.jobs), 0)

    def test_auto_silent_ttl_manual_cooldown_and_units_cache(self):
        self.service.refresh()
        self.finish()
        self.assertFalse(self.events)
        self.request(force=True)
        self.assertFalse(self.jobs)
        self.tick = 61
        self.request(force=True)
        self.assertEqual(len(self.jobs), 1)
        self.finish()
        self.settings.unit_system = "imperial"
        generation = self.service.generation
        self.service.configure(self.settings, LOCATION)
        self.assertEqual(generation, self.service.generation)
        self.assertIsNotNone(self.service.cache)
        self.tick = 1900
        self.service.refresh()
        self.assertEqual(len(self.jobs), 1)

    def test_disable_or_location_change_and_close_while_running(self):
        for action in ("disable", "location", "close"):
            self.setUp()
            self.request()
            if action == "disable":
                self.settings.enabled = False
                self.service.configure(self.settings, LOCATION)
            elif action == "location": self.service.configure(self.settings, Location("x", "x", 0, 0, "UTC"))
            else: self.service.close()
            self.finish()
            self.assertIsNone(self.service.cache)
            self.assertEqual(self.events, ["wait"])

    def test_backoff_retry_after_and_stale_two_hours(self):
        self.service.refresh(); self.finish()
        def fail(*args): raise WeatherError("rate", 600)
        self.provider.fetch = fail
        self.tick = 61
        self.request(force=True); self.finish()
        self.assertTrue(self.events[-1][2])  # manual failure must be disclosed even within TTL
        self.tick = 1900
        self.request(); self.finish()
        self.assertTrue(self.events[-1][2])
        self.assertEqual(self.service.blocked["weather"], 2500)
        self.request(force=True)
        self.assertFalse(self.jobs)
        self.tick = 7201
        self.request(); self.finish()
        self.assertIsNone(self.events[-1][0])

    def test_expired_current_and_forecast_coverage(self):
        self.service.refresh(); self.finish()
        self.service.utcnow = lambda: NOW + timedelta(hours=3)
        self.assertIsNone(self.service.usable("current", stale=True))
        self.service.utcnow = lambda: NOW + timedelta(days=10)
        self.assertIsNone(self.service.usable("future", stale=True))

    def test_air_independent_failure_and_ttl(self):
        self.settings.current["us_aqi"] = True
        self.service.configure(self.settings, LOCATION)
        def fail(*args): raise WeatherError("network")
        self.provider.fetch_air = fail
        self.request()
        self.assertEqual(len(self.jobs), 2)
        self.finish()
        self.assertIsNotNone(self.events[-1][0])
        self.assertIsNone(self.service.air_data())
        self.provider.fetch_air = FakeProvider().fetch_air
        self.tick = 61
        self.service.refresh(); self.finish()
        self.assertIsNotNone(self.service.air_data())
        self.tick = 1900
        self.service.refresh()
        self.assertEqual(len(self.jobs), 1)  # weather expired; AQ still fresh

    def test_network_off_ui_thread_and_no_blocking_close(self):
        entered, release, done = threading.Event(), threading.Event(), threading.Event()
        threads = []
        def fetch(*args):
            threads.append(threading.current_thread())
            entered.set(); release.wait(3); done.set()
            return FakeProvider().fetch(*args)
        self.provider.fetch = fetch
        service = WeatherService(self.provider, lambda *args: None)
        service.configure(self.settings, LOCATION)
        started = time.monotonic()
        service.refresh()
        self.assertLess(time.monotonic()-started, .5)
        self.assertTrue(entered.wait(1))
        service.close()
        self.assertFalse(done.is_set())
        release.set()
        self.assertNotEqual(threads[0], threading.current_thread())

    def test_weather_fields_do_not_invalidate_air_and_air_toggle_keeps_weather(self):
        self.settings.current["us_aqi"] = True
        self.service.configure(self.settings, LOCATION)
        self.service.refresh(); self.finish()
        air = self.service.air
        air_generation = self.service.air_generation
        self.settings.current["pressure_msl"] = True
        self.service.configure(self.settings, LOCATION)
        self.assertIs(self.service.air, air)
        self.assertEqual(self.service.air_generation, air_generation)
        self.tick = 61
        self.service.refresh(); self.finish()
        weather = self.service.cache
        weather_generation = self.service.generation
        self.settings.current["us_aqi"] = False
        self.service.configure(self.settings, LOCATION)
        self.assertIs(self.service.cache, weather)
        self.assertEqual(self.service.generation, weather_generation)
        self.assertIsNone(self.service.air)

    def test_midnight_extends_future_horizon_without_delaying_valid_current(self):
        before = datetime(2026, 11, 20, 20, 50, tzinfo=timezone.utc)
        self.service.utcnow = lambda: before
        zone = ZONES.get_timezone(LOCATION.timezone_id)
        snapshot = parse_weather(fixture(before, zone), zone)
        limited = WeatherSnapshot(snapshot.current, snapshot.hourly, snapshot.daily[:3])
        self.service.cache = CacheEntry(limited, 0)
        self.tick = 1200
        self.service.utcnow = lambda: before + timedelta(minutes=20)
        self.assertIsNotNone(self.service.usable("current"))
        self.assertIsNone(self.service.usable("future"))
        self.assertIsNotNone(self.service.usable("future", stale=True))
        self.request("future")
        self.assertEqual(self.events, ["wait"])
        self.assertEqual(len(self.jobs), 1)


class SettingsTests(unittest.TestCase):
    def test_schema_one_exact_backup_preservation_atomic_write(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"settings.json"
            old = _encode(default_settings()); old.pop("weather"); old["schemaVersion"] = 1
            old["calendar"]["hijriAdjustmentDays"] = 2
            original = json.dumps(old, ensure_ascii=False).encode()
            path.write_bytes(original)
            repository = JsonSettingsRepository(path)
            migrated = repository.load()
            self.assertEqual(path.read_bytes(), original)
            self.assertFalse(migrated.weather.enabled)
            repository.save(migrated)
            self.assertEqual(path.with_name("settings.json.schema1.bak").read_bytes(), original)
            saved = json.loads(path.read_text()); saved.pop("weather"); saved["schemaVersion"] = 1
            self.assertEqual(saved, old)
            self.assertEqual(repository.load(), migrated)

    def test_backup_failure_and_atomic_failure_preserve_original(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"settings.json"
            old = _encode(default_settings()); old.pop("weather"); old["schemaVersion"] = 1
            path.write_text(json.dumps(old))
            before = path.read_bytes()
            with patch("awqati.infrastructure.settings_repository.os.replace", side_effect=OSError("failed")):
                with self.assertRaises(SettingsWriteError): JsonSettingsRepository(path).save(default_settings())
            self.assertEqual(before, path.read_bytes())
            path.write_text('{"schemaVersion": 1}')
            with self.assertRaises(InvalidSettingsDataError): JsonSettingsRepository(path).load()
            self.assertEqual(path.read_text(), '{"schemaVersion": 1}')

    def test_invalid_weather_and_round_trip_custom(self):
        settings = WeatherSettings()
        for key, value in (("future_days", 7), ("upcoming_hours", 24), ("refresh_minutes", True), ("detail", "x")):
            modified = deepcopy(settings); setattr(modified, key, value)
            with self.assertRaises(ValueError): modified.validate()
        settings.custom_units["temperature"] = "kelvin"
        settings.unit_system = "imperial"
        settings.unit_system = "custom"
        self.assertEqual(settings.custom_units["temperature"], "kelvin")

    def test_backup_write_failure_preserves_schema_one_without_partial_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            old = _encode(default_settings()); old.pop("weather"); old["schemaVersion"] = 1
            path.write_text(json.dumps(old))
            before = path.read_bytes()
            real_open = Path.open
            def fail_backup(target, *args, **kwargs):
                if target.name.endswith(".schema1.bak"):
                    raise OSError("backup storage unavailable")
                return real_open(target, *args, **kwargs)
            with patch.object(Path, "open", fail_backup):
                with self.assertRaises(SettingsWriteError): JsonSettingsRepository(path).save(default_settings())
            self.assertEqual(path.read_bytes(), before)
            self.assertFalse(path.with_name("settings.json.schema1.bak").exists())


if __name__ == "__main__": unittest.main()
