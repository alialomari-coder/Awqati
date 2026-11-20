"""Owner-requested weather editorial, snapshot and documentation regressions."""
import ast
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
import unittest

from test_weather import NOW, ZONES, LOCATION, fixture
from awqati.domain.weather import WeatherSettings, WeatherPeriod, WeatherSnapshot
from awqati.infrastructure.weather_provider import parse_weather
from awqati.application.weather_formatters import WeatherFormatter

ROOT = Path(__file__).resolve().parents[1]


class EditorialTests(unittest.TestCase):
    def setUp(self):
        self.settings = WeatherSettings(detail='detailed', upcoming_hours=6)
        self.zone = ZONES.get_timezone(LOCATION.timezone_id)
        self.now = NOW.astimezone(self.zone).replace(hour=23, minute=30)
        self.fmt = WeatherFormatter(self.settings, 'ar', self.zone, self.now)
        self.hours = tuple(WeatherPeriod(self.now.replace(minute=0) + timedelta(hours=i),
            {'temperature_2m': 22, 'weather_code': 0, 'is_day': 0,
             'wind_speed_10m': 1, 'precipitation_probability': 0}) for i in range(1, 7))

    def snapshot(self, hours=None):
        return WeatherSnapshot(None, self.hours if hours is None else hours, ())

    def test_tomorrow_natural_order_all_periods_and_minutes(self):
        for hour in range(24):
            stamp = (self.now + timedelta(days=1)).replace(hour=hour, minute=0)
            label = self.fmt.time_label(stamp, at_hour=True)
            self.assertTrue(label.startswith('غدًا عند الساعة '))
            self.assertNotIn('عند الساعة غدًا', label)
        stamp = (self.now + timedelta(days=1)).replace(hour=1, minute=25)
        self.assertIn('غدًا عند الساعة 1:25 صباحًا', self.fmt.time_label(stamp, at_hour=True))
        self.assertIn('غدًا عند الساعة الثانية عشرة صباحًا', self.fmt.hourly(self.snapshot()))
        self.assertIn('غدًا عند الساعة الواحدة صباحًا', self.fmt.time_label(self.hours[1].time, at_hour=True))

    def test_timezone_date_not_utc_and_later_dates(self):
        midnight = self.hours[0].time
        self.assertEqual(self.fmt.time_label(midnight), self.fmt.time_label(midnight.astimezone(ZONES.get_timezone('UTC'))))
        later = midnight + timedelta(days=1)
        self.assertTrue(self.fmt.time_label(later, at_hour=True).startswith(later.date().isoformat() + ' عند الساعة '))

    def test_today_opening_in_both_languages_and_modes(self):
        data = parse_weather(fixture(), self.zone)
        for lang, city, prefix in [('ar', 'الدمام', 'توقعات الطقس في الدمام اليوم: '),
                                   ('en', 'Dammam', 'Weather forecast for Dammam today: ')]:
            for mode in ['brief', 'detailed']:
                self.settings.detail = mode
                formatter = WeatherFormatter(self.settings, lang, self.zone, NOW)
                for copyable in [False, True]:
                    self.assertTrue(formatter.format(data, 'today', city, copyable=copyable).startswith(prefix))

    def test_dry_speech_once_text_keeps_every_displayed_zero(self):
        before = tuple((p.time, dict(p.values)) for p in self.hours)
        speech = self.fmt.hourly(self.snapshot())
        text = self.fmt.hourly(self.snapshot(), copyable=True)
        self.assertEqual(speech.count('لا يُتوقع هطول'), 1)
        self.assertNotIn('احتمال هطول', speech)
        self.assertEqual(text.count('احتمال هطول 0 بالمئة'), 4)
        self.assertEqual(before, tuple((p.time, dict(p.values)) for p in self.hours))

    def test_unknown_and_positive_unsampled_hours_prevent_dry_summary(self):
        for value in [None, 1, 75]:
            hours = tuple(WeatherPeriod(p.time, dict(p.values)) for p in self.hours)
            if value is None: hours[1].values.pop('precipitation_probability')
            else: hours[1].values['precipitation_probability'] = value
            speech = self.fmt.hourly(self.snapshot(hours))
            self.assertNotIn('لا يُتوقع هطول', speech)
            self.assertIn('احتمال هطول', speech)
        hours = tuple(WeatherPeriod(p.time, dict(p.values)) for p in self.hours)
        hours[0].values['precipitation_probability'] = 75
        self.assertIn('75 بالمئة', self.fmt.hourly(self.snapshot(hours)))

    def test_partial_data_summary_bounds_are_explicit_and_no_empty_claim(self):
        text = self.fmt.hourly(self.snapshot(self.hours[:2]))
        self.assertIn('من ' + self.fmt.range_time_label(self.hours[0].time), text)
        self.assertIn('حتى ' + self.fmt.range_time_label(self.hours[1].time), text)
        self.assertNotIn(self.fmt.time_label(self.hours[-1].time), text)
        self.assertEqual(self.fmt.hourly(self.snapshot(())), '')


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        tree = ast.parse((ROOT/'addon/globalPlugins/awqati/nvda_adapter/weather_control.py').read_text('utf-8'))
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'WeatherControl')
        # Execute production lifecycle methods without importing NVDA/wx.
        self.dialog = SimpleNamespace(_instance=None)
        ns = {'WeatherTextDialog': self.dialog}
        exec(compile(ast.Module(body=[cls], type_ignores=[]), '<weather-control>', 'exec'), ns)
        self.ctrl = ns['WeatherControl'].__new__(ns['WeatherControl'])
        c = self.ctrl
        c.closed = False; c.serial = 0; c.last_report = 'current'; c.last_success_text = None
        c.language = lambda: 'ar'
        c.presses = SimpleNamespace(close=lambda: None)
        self.requests=[]; self.messages=[]; self.windows=[]
        c.speak=self.messages.append; c._show=self.windows.append
        c.service=SimpleNamespace(cancel_speech=lambda: None, air_data=lambda: None,
            request=lambda *args: self.requests.append(args))
        self.settings=WeatherSettings(detail='detailed')
        self.zone=ZONES.get_timezone(LOCATION.timezone_id)
        c.formatter=lambda: WeatherFormatter(self.settings, 'ar', self.zone, NOW)
        c.location_name=lambda: 'الدمام'
        self.data=parse_weather(fixture(),self.zone)

    def request(self, report, data=None, error=None, stale=False):
        self.ctrl.select(report)
        self.requests[-1][1](data, error, stale)

    def test_no_prior_success_never_fetches(self):
        self.ctrl.show()
        self.assertFalse(self.requests);self.assertFalse(self.windows)
        self.assertIn('اطلب تقريرًا أولًا', self.messages[-1])

    def test_snapshot_survives_failures_settings_mutation_and_refresh(self):
        self.request('today',self.data)
        expected=self.ctrl.last_success_text
        self.assertIn('توقعات الطقس',expected)
        self.assertIn('CC BY 4.0',expected)
        self.settings.unit_system='imperial';self.settings.detail='brief'
        self.request('future',error='network')
        self.ctrl.show()
        self.assertEqual(self.windows[-1],expected)
        self.assertEqual(len(self.requests),2)
        self.request('future', WeatherSnapshot(None,(),()))
        self.assertEqual(self.ctrl.last_success_text,expected)
        self.ctrl.service.request=lambda *args: self.fail('window must not request data')
        self.ctrl.show();self.assertEqual(self.windows[-1],expected)

    def test_success_replaces_snapshot_only_after_completion_and_cancel_ignored(self):
        self.request('current',self.data)
        previous=self.ctrl.last_success_text
        self.ctrl.select('today'); callback=self.requests[-1][1]
        self.assertEqual(self.ctrl.last_success_text,previous)
        self.ctrl.cancel();callback(self.data,None,False)
        self.assertEqual(self.ctrl.last_success_text,previous)
        self.request('future',self.data,stale=True)
        self.assertNotEqual(self.ctrl.last_success_text,previous)
        self.assertIn('بيانات محفوظة',self.ctrl.last_success_text)

    def test_existing_window_refocused_without_request(self):
        self.dialog._instance=object()
        self.ctrl.show()
        self.assertEqual(self.windows,['']);self.assertFalse(self.requests)


class GuideTests(unittest.TestCase):
    def test_overview_exact_and_weather_before_reminders_once(self):
        ar=(ROOT/'docs/دليل_أوقاتي_العربي_المعتمد.md').read_text('utf-8')
        generated=(ROOT/'addon/doc/ar/readme.md').read_text('utf-8')
        self.assertEqual(ar,generated)
        import hashlib
        overview = ar.split('# طريقة الاستخدام')[0].split('\n\n',1)[1].strip()
        self.assertEqual(hashlib.sha256(overview.encode('utf-8')).hexdigest(), 'cbeaf61db5948689d60e04c135163b8f8afd842f8d98e39afa5516fd533be9fd')
        for path,calendar,weather,adhkar,history in [
            ('docs/دليل_أوقاتي_العربي_المعتمد.md','## التقويم','## الطقس','## تنبيهات الأذكار','# سجل التغييرات'),
            ('addon/doc/en/readme.md','## Calendar','## Weather','## Dhikr alerts','# Change')]:
            text=(ROOT/path).read_text('utf-8')
            self.assertEqual(text.count(weather+'\n'),1)
            self.assertLess(text.index(calendar+'\n'),text.index(weather+'\n'))
            self.assertLess(text.index(weather+'\n'),text.index(adhkar+'\n'))
            self.assertNotIn('# Weather service — Awqati 8.0.0',text)
            self.assertNotIn('# خدمة الطقس — أوقاتي 8.0.0',text)
            section=text.split(weather+'\n',1)[1].split(adhkar+'\n',1)[0]
            self.assertEqual(section.count('\n### '),11)
            for token in ['NVDA+Alt+W','NVDA+W','CAMS','CC BY 4.0','Control+A','Control+C','settings.json.schema1.bak','Retry-After']:
                self.assertIn(token,section)

    def test_command_labels_match_without_shortcut_in_description(self):
        english='Open weather information in a text window';arabic='فتح معلومات الطقس في نافذة نصية'
        for path in ['addon/globalPlugins/awqati/nvda_adapter/weather_control.py','addon/locale/ar/LC_MESSAGES/nvda.po']:
            text=(ROOT/path).read_text('utf-8');self.assertIn(english,text);self.assertIn(arabic,text)
        tree=ast.parse((ROOT/'addon/globalPlugins/awqati/nvda_adapter/plugin.py').read_text('utf-8'))
        fn=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='script_weatherReport')
        desc=next(k.value.args[0].value for d in fn.decorator_list for k in d.keywords if k.arg=='description')
        self.assertEqual(desc,english);self.assertNotIn('NVDA',desc)
