"""Regression coverage for the owner's weather listening and text corrections."""
from copy import deepcopy
from datetime import timedelta
import ast
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from test_weather import NOW, ZONES, LOCATION, fixture
from awqati.domain import default_settings
from awqati.domain.weather import WeatherSettings, WeatherPeriod, WeatherSnapshot, description, requested_fields
from awqati.application.weather_formatters import WeatherFormatter
from awqati.infrastructure.weather_provider import parse_weather
from awqati.infrastructure.settings_repository import JsonSettingsRepository, _encode, InvalidSettingsDataError

ROOT = Path(__file__).resolve().parents[1]


class WeatherCorrectionTests(unittest.TestCase):
    def setUp(self):
        self.zone = ZONES.get_timezone(LOCATION.timezone_id)
        self.settings = WeatherSettings()
        raw = fixture()
        raw['current'].update(is_day=1, weather_code=0, temperature_2m=28.5)
        raw['current_units']['is_day'] = ''
        self.snapshot = parse_weather(raw, self.zone)

    def fmt(self, language='ar', report='current', **kwargs):
        return WeatherFormatter(self.settings, language, self.zone, NOW).format(
            self.snapshot, report, 'الدمام' if language == 'ar' else 'Dammam', **kwargs)

    def test_brief_core_only_and_rounding(self):
        text = self.fmt()
        for item in ('أحوال الطقس في الدمام اليوم', 'مشمس', '29 درجة مئوية', 'العظمى المتوقعة 26', 'الصغرى المتوقعة 17'):
            self.assertIn(item, text)
        for item in ('المحسوسة', 'رياح', 'الرطوبة', 'Open-Meteo', '28.5'):
            self.assertNotIn(item, text)
        self.assertEqual(text.count('درجة مئوية'), 1)

    def test_detailed_includes_extremes_and_optional_feels_like(self):
        self.settings.detail = 'detailed'
        self.assertIn('28.5', self.fmt())
        self.assertIn('العظمى المتوقعة', self.fmt())
        self.assertIn('الحرارة المحسوسة', self.fmt())
        self.settings.current['apparent_temperature'] = False
        self.assertNotIn('المحسوسة', self.fmt())
        self.assertNotIn('apparent_temperature', requested_fields(self.settings)[0])

    def test_day_night_and_daily_aggregate(self):
        self.assertEqual(description(0, True, 1), 'مشمس')
        self.assertEqual(description(0, True, 0), 'صافٍ')
        self.assertEqual(description(0, False, 1), 'sunny')
        self.assertEqual(description(0, False, 0), 'clear')
        self.assertEqual(description(0, True), 'صافٍ')
        self.assertEqual(description(61, True, 1), 'أمطار خفيفة')
        formatter = WeatherFormatter(self.settings, 'ar', self.zone, NOW)
        self.assertNotIn('مشمس', formatter.daily(WeatherPeriod(NOW, {'weather_code': 0}), self.settings.today))

    def test_daylight_is_validated_and_requested_for_each_instant(self):
        for fields in requested_fields(self.settings)[:2]: self.assertIn('is_day', fields)
        for value in (2, -1, True, '1', None):
            raw = fixture(); raw['current']['is_day'] = value; raw['current_units']['is_day'] = ''
            self.assertNotIn('is_day', parse_weather(raw, self.zone).current.values)

    def test_speech_omits_credits_and_text_keeps_them(self):
        self.settings.detail = 'detailed'; self.settings.current['us_aqi'] = True
        for lang in ('ar', 'en'):
            for report in ('current', 'today', 'future'):
                speech = self.fmt(lang, report, air=WeatherPeriod(NOW, {'us_aqi': 124}))
                self.assertNotIn('Open-Meteo', speech); self.assertNotIn('CAMS', speech)
                text = self.fmt(lang, report, air=WeatherPeriod(NOW, {'us_aqi': 124}), copyable=True)
                self.assertIn('Open-Meteo', text); self.assertIn('CC BY 4.0', text)
                self.assertIn('creativecommons.org', text)
                if report == 'current': self.assertIn('CAMS', text)

    def test_text_lines_and_aqi_punctuation(self):
        self.settings.detail = 'detailed'; self.settings.current = dict.fromkeys(self.settings.current, True)
        text = self.fmt(copyable=True, air=WeatherPeriod(NOW, {'us_aqi': 124}))
        lines = text.splitlines()
        self.assertTrue(lines[0].startswith('أحوال الطقس في الدمام'))
        self.assertTrue(lines[1].startswith('الحالة الجوية: مشمس'))
        self.assertTrue(any(line.startswith('درجة الحرارة الحالية:') for line in lines))
        self.assertIn('124، غير صحي للفئات الحساسة', text)
        self.assertIn('10 كيلومتر', text)
        self.assertGreater(len(lines), 16)

    def test_precipitation_interval_is_not_fixed(self):
        self.settings.detail = 'detailed'; self.settings.current['precipitation'] = True
        for interval, minutes in ((900, '15'), (1800, '30'), (3600, '60')):
            self.snapshot = WeatherSnapshot(WeatherPeriod(NOW, {'temperature_2m': 20, 'precipitation': 0}, interval), (), ())
            self.assertIn('الهطول خلال آخر ' + minutes + ' دقيقة', self.fmt())
        self.snapshot = WeatherSnapshot(WeatherPeriod(NOW, {'temperature_2m': 20, 'precipitation': 0}), (), ())
        self.assertNotIn('الهطول', self.fmt())

    def test_missing_values_are_omitted_without_fake_extremes(self):
        self.snapshot = WeatherSnapshot(WeatherPeriod(NOW, {'weather_code': 0}), (), ())
        text = self.fmt()
        self.assertNotIn('درجة', text); self.assertNotIn('None', text)
        self.snapshot = WeatherSnapshot(WeatherPeriod(NOW, {'temperature_2m': -2.5}), (), ())
        self.assertIn('-3 درجة مئوية', self.fmt())
        self.assertNotIn('الجو', self.fmt())

    def test_units_rounding_preserves_original_values(self):
        before = dict(self.snapshot.current.values)
        for unit, brief, detailed in (('kelvin', '302', '301.7'), ('fahrenheit', '83', '83.3'), ('celsius', '29', '28.5')):
            self.settings.unit_system = 'custom'; self.settings.custom_units['temperature'] = unit
            self.settings.detail = 'brief'; self.assertIn(brief, self.fmt())
            self.settings.detail = 'detailed'; self.assertIn(detailed, self.fmt())
        self.assertEqual(before, self.snapshot.current.values)

    def test_hourly_full_horizon_partial_data_and_midnight(self):
        self.settings.detail = 'detailed'
        for horizon, expected in ((3, 3), (6, 4), (12, 5)):
            self.settings.upcoming_hours = horizon
            formatter = WeatherFormatter(self.settings, 'en', self.zone, NOW)
            text = formatter.hourly(self.snapshot, copyable=True)
            self.assertEqual(text.count('At '), expected)
            self.assertIn(formatter.time_label(NOW + timedelta(hours=horizon)), text)
            self.assertEqual(len(text.splitlines()), expected)
        partial = WeatherSnapshot(self.snapshot.current, self.snapshot.hourly[:2], ())
        self.assertEqual(formatter.hourly(partial).count('At '), 2)
        self.settings.hourly_periods = False
        self.assertLessEqual(formatter.hourly(self.snapshot).count('At '), 1)

    def test_city_once_in_future_report(self):
        for lang, name in (('ar', 'الدمام'), ('en', 'Dammam')):
            for copyable in (False, True):
                text = self.fmt(lang, 'future', copyable=copyable)
                self.assertEqual(text.count(name), 1)

    def test_actual_bundled_dammam_names_preserve_identity(self):
        from awqati.infrastructure import BundledLocationRepository
        from awqati.nvda_adapter.location_labels import city_name
        repo = BundledLocationRepository()
        match = repo.search('SA', 'Dammam')[0]
        location = match.location
        self.assertEqual(city_name(match, 'ar'), 'الدمام')
        self.assertEqual(city_name(match, 'en'), 'Dammam')
        self.assertEqual(repo.get('SA', location.location_id).location, location)

    def test_hourly_midnight_uses_site_date_and_never_sunny_at_night(self):
        local_now = NOW.astimezone(self.zone).replace(hour=23, minute=30)
        hour = local_now.replace(hour=0, minute=0) + timedelta(days=1)
        self.settings.detail = 'detailed'
        formatter = WeatherFormatter(self.settings, 'en', self.zone, local_now)
        snapshot = WeatherSnapshot(None, (WeatherPeriod(hour, {'weather_code': 0, 'is_day': 0, 'temperature_2m': 20}),), ())
        text = formatter.hourly(snapshot)
        self.assertIn('tomorrow 12 AM', text)
        self.assertIn('clear', text); self.assertNotIn('sunny', text)

    def test_daily_information_obeys_detail_and_never_waits_for_network(self):
        from datetime import datetime, timezone
        class Clock(datetime):
            @classmethod
            def now(cls, zone=None): return NOW
        tree = ast.parse((ROOT / 'addon/globalPlugins/awqati/nvda_adapter/weather_control.py').read_text('utf-8'))
        method = next(n for cls in tree.body if isinstance(cls, ast.ClassDef) and cls.name == 'WeatherControl'
                      for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'summary')
        ns = dict(WeatherFormatter=WeatherFormatter, deepcopy=deepcopy, datetime=Clock, timezone=timezone)
        exec(compile(ast.Module(body=[method], type_ignores=[]), '<summary>', 'exec'), ns)
        calls = []
        service = SimpleNamespace(enabled=True, settings=self.settings, location=LOCATION,
            usable=lambda report: SimpleNamespace(data=self.snapshot), air_data=lambda: None,
            refresh=lambda: calls.append('background'))
        obj = SimpleNamespace(service=service, zones=ZONES, location_name=lambda language: 'الدمام')
        self.settings.include_in_daily_info = True
        self.assertNotIn('المحسوسة', ns['summary'](obj, 'ar'))
        self.settings.detail = 'detailed'
        self.assertIn('المحسوسة', ns['summary'](obj, 'ar'))
        self.settings.current['apparent_temperature'] = False
        self.assertNotIn('المحسوسة', ns['summary'](obj, 'ar'))
        self.assertNotIn('Open-Meteo', ns['summary'](obj, 'ar'))
        self.assertFalse(calls)
        service.usable = lambda report: None
        self.assertEqual(ns['summary'](obj, 'ar'), '')
        self.assertEqual(calls, ['background'])

    def test_schema_two_upgrade_preserves_saved_choices_and_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'settings.json'
            raw = _encode(default_settings()); raw['weather']['current'].pop('apparent_temperature')
            raw['weather']['current']['pressure_msl'] = True
            original = json.dumps(raw).encode(); path.write_bytes(original)
            repo = JsonSettingsRepository(path); settings = repo.load()
            self.assertTrue(settings.weather.current['apparent_temperature'])
            self.assertTrue(settings.weather.current['pressure_msl'])
            self.assertEqual(path.read_bytes(), original)
            settings.weather.current['apparent_temperature'] = False
            repo.save(settings); self.assertFalse(repo.load().weather.current['apparent_temperature'])

    def test_unknown_weather_choice_is_still_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'settings.json'; raw = _encode(default_settings())
            raw['weather']['current']['typo'] = True; path.write_text(json.dumps(raw))
            with self.assertRaises(InvalidSettingsDataError): JsonSettingsRepository(path).load()

    def test_location_uses_existing_labels_and_retains_custom_names(self):
        # Exercise production name resolver without importing NVDA/wx host modules.
        from awqati.nvda_adapter.location_labels import city_name
        tree = ast.parse((ROOT / 'addon/globalPlugins/awqati/nvda_adapter/weather_control.py').read_text('utf-8'))
        method = next(n for cls in tree.body if isinstance(cls, ast.ClassDef) and cls.name == 'WeatherControl'
                      for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'location_name')
        ns = {'city_name': city_name}; exec(compile(ast.Module(body=[method], type_ignores=[]), '<resolver>', 'exec'), ns)
        match = SimpleNamespace(arabic_names=('الدمام',), english_names=('Dammam',), location=SimpleNamespace(name='Dammam'))
        stored = SimpleNamespace(kind=SimpleNamespace(value='selected'), country_code='SA', location=SimpleNamespace(location_id='id'))
        calls = []
        obj = SimpleNamespace(settings=SimpleNamespace(runtime_settings=SimpleNamespace(location=stored)),
            service=SimpleNamespace(location=SimpleNamespace(name='User name')),
            locations=SimpleNamespace(get=lambda *args: calls.append(args) or match), language=lambda: 'ar')
        self.assertEqual(ns['location_name'](obj), 'الدمام')
        self.assertEqual(ns['location_name'](obj, 'en'), 'Dammam')
        self.assertEqual(calls, [('SA', 'id'), ('SA', 'id')])
        stored.kind.value = 'custom'; self.assertEqual(ns['location_name'](obj), 'User name')
