"""Only the three owner-requested Arabic weather wording corrections."""
from datetime import timedelta
import re
import unittest

from test_weather import NOW, ZONES, LOCATION, fixture
from awqati.domain.weather import WeatherSettings, WeatherPeriod, WeatherSnapshot
from awqati.infrastructure.weather_provider import parse_weather
from awqati.application.weather_formatters import WeatherFormatter


class WordingTests(unittest.TestCase):
    def setUp(self):
        self.settings = WeatherSettings(detail='detailed', upcoming_hours=12)
        self.settings.current = dict.fromkeys(self.settings.current, True)
        self.zone = ZONES.get_timezone(LOCATION.timezone_id)
        self.now = NOW.astimezone(self.zone).replace(hour=18, minute=30)
        self.fmt = WeatherFormatter(self.settings, 'ar', self.zone, self.now)
        self.data = parse_weather(fixture(), self.zone)

    def dry(self, start, count):
        hours = tuple(WeatherPeriod(start + timedelta(hours=i), dict(precipitation_probability=0)) for i in range(count))
        return WeatherSnapshot(None, hours, ())

    def test_current_preserves_every_selected_part_and_order(self):
        air = WeatherPeriod(self.now, dict(us_aqi=42))
        def values():
            return [(p.time, dict(p.values), p.interval) for p in
                    (self.data.current, *self.data.hourly, *self.data.daily)]
        before = values()
        for units in ('metric', 'imperial', 'custom'):
            self.settings.unit_system = units
            fmt = WeatherFormatter(self.settings, 'ar', self.zone, self.now)
            parts = fmt.current_parts(self.data.current, self.data.daily[0], air)
            report = fmt.format(self.data, 'current', 'الرياض', air)
            self.assertEqual(report, 'أحوال الطقس في الرياض: ' + '. '.join(parts) + '.')
            self.assertNotIn('، و', report)
            text_parts = fmt.current_parts(self.data.current, self.data.daily[0], air, True)
            text = fmt.format(self.data, 'current', 'الرياض', air, copyable=True)
            self.assertTrue(text.startswith('أحوال الطقس في الرياض\n' + '.\n'.join(text_parts) + '.'))
            self.assertEqual(re.findall(r'\d+(?:\.\d+)?', report), re.findall(r'\d+(?:\.\d+)?', '. '.join(parts)))
        self.assertEqual(before, values())

    def test_disabled_current_options_remain_absent(self):
        self.settings.current = dict.fromkeys(self.settings.current, False)
        report = self.fmt.format(self.data, 'current', 'الرياض')
        for word in ('المحسوسة', 'الرطوبة', 'هبات', 'الضغط', 'الرؤية', 'الهطول', 'مؤشر'):
            self.assertNotIn(word, report)

    def test_cross_midnight_exact_natural_range(self):
        data = self.dry(self.now.replace(hour=19, minute=0), 12)
        report = self.fmt.hourly(data)
        self.assertTrue(report.startswith('لا يُتوقع هطول أمطار خلال الفترة الممتدة من السابعة مساءً حتى السادسة من صباح الغد.'))
        self.assertNotIn('القراءات الساعية', report)
        self.assertEqual(report.count('لا يُتوقع'), 1)

    def test_same_day_and_morning_evening_transition(self):
        now = self.now.replace(hour=10, minute=30)
        fmt = WeatherFormatter(self.settings, 'ar', self.zone, now)
        report = fmt.hourly(self.dry(now.replace(hour=11, minute=0), 8))
        self.assertIn('من الحادية عشرة صباحًا حتى السادسة مساءً', report)
        self.assertNotIn('الغد', report)

    def test_all_hours_minutes_timezone_and_tomorrow(self):
        for hour in range(24):
            stamp = (self.now + timedelta(days=1)).replace(hour=hour, minute=0)
            text = self.fmt.range_time_label(stamp)
            self.assertIn('الغد', text)
            self.assertNotIn('عند الساعة', text)
            self.assertEqual(text, self.fmt.range_time_label(stamp.astimezone(ZONES.get_timezone('UTC'))))
        self.assertEqual(self.fmt.range_time_label(self.now.replace(hour=19, minute=25)), '7:25 مساءً')

    def test_insufficient_unknown_and_positive_data_keep_dry_rules(self):
        self.assertEqual(self.fmt.hourly(WeatherSnapshot(None, (), ())), '')
        for value in (None, 1, 75):
            data = self.dry(self.now.replace(hour=19, minute=0), 3)
            if value is None:
                data.hourly[1].values.clear()
            else:
                data.hourly[1].values['precipitation_probability'] = value
            # An empty hour is filtered by the existing logic; a nonempty
            # unknown probability must prevent the zero summary.
            if value is None:
                data.hourly[1].values['temperature_2m'] = 20
            self.assertNotIn('لا يُتوقع', self.fmt.hourly(data))
        single = self.dry(self.now.replace(hour=19, minute=0), 1)
        self.assertIn('من السابعة مساءً حتى السابعة مساءً', self.fmt.hourly(single))

    def test_maximum_zero_positive_today_future_and_partial(self):
        for value, spoken in ((0, 'صفر'), (37, '37'), (100, '100')):
            for period in self.data.daily:
                period.values['precipitation_probability_max'] = value
            # The phrase explicitly limits its claim to available hours,
            # even when no hourly detail accompanies the daily aggregate.
            for hours in ((), self.data.hourly[:2], self.data.hourly):
                data = WeatherSnapshot(self.data.current, hours, self.data.daily)
                for report in ('today', 'future'):
                    for copyable in (False, True):
                        text = self.fmt.format(data, report, 'الرياض', copyable=copyable)
                        expected = 'أعلى احتمال لهطول الأمطار خلال إحدى ساعات اليوم المتاحة: ' + spoken + ' بالمئة'
                        self.assertIn(expected, text)
                        self.assertNotIn('أعلى احتمال هطول ساعي', text)
            self.assertEqual(self.data.daily[0].values['precipitation_probability_max'], value)

    def test_english_wording_unchanged(self):
        fmt = WeatherFormatter(self.settings, 'en', self.zone, self.now)
        self.assertIn('highest hourly precipitation probability 0 percent', fmt.daily(self.data.daily[0], self.settings.today))
        self.assertIn('No rain is expected in the available hourly readings from 7 PM to tomorrow 6 AM', fmt.hourly(self.dry(self.now.replace(hour=19, minute=0), 12)))
