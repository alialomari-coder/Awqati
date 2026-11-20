"""Focused packaged wording and text-window smoke check, no network requests."""
from datetime import datetime, timedelta, timezone
import importlib
from pathlib import Path
import sys
import globalVars
import wx
ROOT = Path((Path(globalVars.appArgs.configPath) / 'source-root.txt').read_text('utf-8'))
sys.path[:0] = [str(ROOT/'tools'), str(ROOT/'tests')]
from weather_801_nvda_probe import GlobalPlugin as WeatherProbe
from support.weather_fixtures import fixture


class GlobalPlugin(WeatherProbe):
    def scenarios(self):
        yield 100
        fmt_module = importlib.import_module(self.prefix + '.application.weather_formatters')
        zone = self.weather.zones.get_timezone('Asia/Riyadh')
        now = datetime.now(timezone.utc).astimezone(zone).replace(hour=18, minute=30)
        settings = self.settings_module.WeatherSettings(detail='detailed', upcoming_hours=12)
        fmt = fmt_module.WeatherFormatter(settings, self.result['language'], zone, now)
        data = self.provider_module.parse_weather(fixture(now, zone), zone)
        self.weather.formatter = lambda: fmt
        self.weather.location_name = lambda: 'الرياض' if fmt.ar else 'Riyadh'
        self.weather.service.request = lambda report, ready, waiting, force: ready(data, None, False)
        for report in ('current', 'today', 'future'):
            self.weather.select(report)
            speech = self.messages[-1]
            self.require(bool(speech) and bool(self.weather.last_success_text), report + ' formatted in actual NVDA')
            if fmt.ar and report == 'current':
                self.require('، و' not in speech and '. ' in speech, 'detailed Arabic sentences separated naturally')
            elif fmt.ar:
                self.require('أعلى احتمال لهطول الأمطار خلال إحدى ساعات اليوم المتاحة: صفر بالمئة' in speech, report + ' maximum probability wording')
        hours = tuple(self.settings_module.WeatherPeriod(now.replace(hour=19, minute=0) + timedelta(hours=i),
            dict(precipitation_probability=0)) for i in range(12))
        if fmt.ar:
            self.require('من السابعة مساءً حتى السادسة من صباح الغد' in fmt.hourly(self.settings_module.WeatherSnapshot(None, hours, ())), 'natural midnight boundary in packaged formatter')
        self.weather.select('current')
        expected = self.weather.last_success_text
        self.weather.service.request = lambda *args: self.require(False, 'text window must not fetch')
        self.weather.show()
        yield 300
        dialog = self.control_module.WeatherTextDialog._instance
        self.require(dialog is not None, 'actual weather text window opened')
        self.require(dialog.text.GetValue().replace('\r\n', '\n') == expected, 'window contains exact successful formatted report')
        self.require(wx.Window.FindFocus() is dialog.text, 'report text receives keyboard focus')
        self.require(bool(self.obj(dialog.text).value), 'actual NVDA accessible text value is available')
        dialog.Close()
        yield 150
        self.require(self.control_module.WeatherTextDialog._instance is None, 'weather window closes normally')
