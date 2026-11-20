"""Extend the existing real-NVDA probe for the 8.0.2 review snapshot."""
from pathlib import Path
import sys
import globalVars

ROOT = Path((Path(globalVars.appArgs.configPath) / 'source-root.txt').read_text('utf-8'))
sys.path[:0] = [str(ROOT/'tools'), str(ROOT/'tests')]
from weather_801_nvda_probe import GlobalPlugin as Weather801Probe
from datetime import datetime, timedelta, timezone
import importlib


class GlobalPlugin(Weather801Probe):
    def scenarios(self):
        # No data request or worker may be started by opening an empty review.
        old = self.weather.service.request
        self.weather.service.request = lambda *args: self.require(False, 'empty text window must not request data')
        self.weather.show()
        self.require(self.messages[-1] in (
            'لا توجد معلومات طقس سابقة؛ اطلب تقريرًا أولًا',
            'No previous weather information; request a report first'), 'empty review gives localized instruction')
        self.weather.service.request = old
        self.messages.clear()
        checked = False
        for delay in super().scenarios():
            yield delay
            dialog = self.control_module.WeatherTextDialog._instance
            if checked or not dialog:
                continue
            checked = True
            expected = self.weather.last_success_text
            self.require(dialog.text.GetValue().replace('\r\n','\n') == expected, 'text window matches frozen successful forecast')
            old = self.weather.service.request
            self.weather.service.request = lambda report, ready, waiting, force: ready(None, 'network', False)
            self.weather.select('today')
            self.require(self.weather.last_success_text == expected, 'failed last request preserves successful forecast')
            self.weather.service.request = lambda *args: self.require(False, 'opening review must never fetch')
            self.weather.show()
            self.require(dialog.text.GetValue().replace('\r\n','\n') == expected, 'failed query and reopen preserve open contents')
            self.weather.service.request = old
            expected_name = 'فتح معلومات الطقس في نافذة نصية' if self.result['language'].startswith('ar') else 'Open weather information in a text window'
            self.require(self.plugin.script_weatherReport.__doc__ == expected_name, 'Input Gestures uses unified localized label without shortcut')
            self.require(expected_name in [item.GetItemLabel() for item in self.weather.weather_menu.GetMenuItems()], 'menu matches localized Input Gestures label')
            formatter_module = importlib.import_module(self.prefix + '.application.weather_formatters')
            now = datetime.now(timezone.utc).astimezone(self.weather.formatter().zone).replace(hour=23, minute=30)
            settings = self.settings_module.WeatherSettings(detail='detailed', upcoming_hours=3)
            formatter = formatter_module.WeatherFormatter(settings, self.result['language'], self.weather.formatter().zone, now)
            hours = tuple(self.settings_module.WeatherPeriod(now.replace(minute=0) + timedelta(hours=i),
                dict(weather_code=0, is_day=0, temperature_2m=20, wind_speed_10m=1, precipitation_probability=0)) for i in (1,2,3))
            snapshot = self.settings_module.WeatherSnapshot(None, hours, ())
            speech = formatter.hourly(snapshot)
            text = formatter.hourly(snapshot, copyable=True)
            self.require(('احتمال هطول' not in speech) if formatter.ar else ('precipitation probability' not in speech), 'all-zero spoken probabilities condensed')
            self.require(text.count('احتمال هطول' if formatter.ar else 'precipitation probability') == 3, 'text preserves all hourly zero values')
            if formatter.ar:
                self.require('غدًا عند الساعة الواحدة صباحًا' in speech and 'عند الساعة غدًا' not in speech, 'Arabic next-day time ordering in packaged formatter')
        self.require(checked, 'extended snapshot checks actually ran')
