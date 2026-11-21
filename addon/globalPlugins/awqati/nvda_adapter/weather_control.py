"""Weather-only UI lifecycle, settled multi-press command and independent text window."""
from copy import deepcopy
from datetime import datetime, timezone

import wx
import gui
from ..domain import SettingsApplied
from ..application.weather_service import WeatherService
from ..application.weather_formatters import WeatherFormatter, SOURCE_LINKS, AIR_LINK
from ..infrastructure.weather_provider import OpenMeteoProvider
from .text_dialog import SelectableTextDialog
from .location_labels import city_name


# Temporary 8.2.2 decision: menu execution interrupts speech, while gestures work.
# Set to True in a later release to restore both retained Tools submenus.
TOOLS_MENU_ENABLED = False


class WeatherTextDialog(SelectableTextDialog):
    # Keep weather and other report windows completely independent.
    _instance = None
    copy_report = True


class WeatherPresses:
    def __init__(self, schedule, timeout, select, cancel):
        self.schedule, self.timeout, self.select, self.cancel = schedule, timeout, select, cancel
        self.timer = None
        self.count = 0
        self.serial = 0

    def press(self):
        self.cancel()
        self.count = min(3, self.count + 1)
        self.serial += 1
        token = self.serial
        if self.timer: self.timer.Stop()
        self.timer = self.schedule(max(250, int(self.timeout())) + 50, self._settle, token)

    def _settle(self, token):
        if token != self.serial: return
        report = ("current", "today", "future")[max(0, self.count - 1)]
        self.count, self.timer = 0, None
        self.select(report)

    def close(self):
        self.serial += 1
        self.count = 0
        if self.timer: self.timer.Stop()
        self.timer = None


class WeatherControl:
    def __init__(self, settings, zones, language, speak, timeout, locations=None):
        self.locations = locations
        self.settings, self.zones, self.language, self.speak = settings, zones, language, speak
        self.service = WeatherService(OpenMeteoProvider(zones), wx.CallAfter)
        self.last_report = "current"
        self.last_success_text = None
        self.timer = None
        self.closed = False
        self.serial = 0
        self.presses = WeatherPresses(wx.CallLater, timeout, self.select, self.cancel)
        self.unsubscribe = settings.events.subscribe(SettingsApplied, self._applied)
        self._applied()
        self.menu_item = None
        if TOOLS_MENU_ENABLED:
            self._install_menu()

    def tr(self, ar, en): return ar if self.language().startswith("ar") else en

    def _install_menu(self):
        self.menu = wx.Menu()
        self.weather_menu = wx.Menu()
        actions = (("الحالة الحالية", "Current weather", lambda: self.select("current")),
                   ("توقعات اليوم", "Today's forecast", lambda: self.select("today")),
                   ("توقعات الأيام القادمة", "Coming days forecast", lambda: self.select("future")),
                   ("فتح معلومات الطقس في نافذة نصية", "Open weather information in a text window", self.show),
                   ("تحديث الآن", "Refresh now", self.refresh_now))
        for ar, en, action in actions:
            item = self.weather_menu.Append(wx.ID_ANY, self.tr(ar, en))
            self.menu.Bind(wx.EVT_MENU, lambda event, action=action: action(), item)
        self.menu.AppendSubMenu(self.weather_menu, self.tr("الطقس", "Weather"))
        self.menu_item = gui.mainFrame.sysTrayIcon.toolsMenu.AppendSubMenu(self.menu, self.tr("أوقاتي", "Awqati"))

    def cancel(self):
        self.serial += 1
        self.service.cancel_speech()

    def _applied(self, event=None):
        self.cancel()
        self.presses.close()
        current = self.settings.runtime_settings
        self.service.configure(current.weather, current.location.location if current.location else None)
        if self.timer: self.timer.Stop()
        self.timer = None
        if self.service.enabled:
            self.service.refresh()
            self.timer = wx.CallLater(self.service.next_tick_ms(), self._tick)

    def _tick(self):
        self.timer = None
        if self.closed or not self.service.enabled: return
        self.service.refresh()
        self.timer = wx.CallLater(self.service.next_tick_ms(), self._tick)

    def formatter(self):
        return WeatherFormatter(self.service.settings, self.language(),
            self.zones.get_timezone(self.service.location.timezone_id), datetime.now(timezone.utc))

    def location_name(self, language=None):
        stored = self.settings.runtime_settings.location
        if stored and stored.kind.value == "selected" and self.locations:
            match = self.locations.get(stored.country_code, stored.location.location_id)
            if match:
                return city_name(match, language or self.language())
        return self.service.location.name

    def select(self, report=None, text=False, force=False):
        if self.closed: return
        self.presses.close()
        self.cancel()
        token = self.serial
        self.last_report = report or self.last_report
        selected = self.last_report
        def ready(data, error, stale):
            if self.closed or token != self.serial: return
            if data is None:
                message = {
                    "disabled": self.tr("خدمة الطقس معطلة", "Weather service is disabled"),
                    "location": self.tr("يرجى تعيين موقع أوقاتي أولًا", "Please assign an Awqati location first"),
                    "rate": self.tr("يرجى المحاولة لاحقًا؛ مصدر الطقس يقيّد الطلبات", "Please try later; the weather source is limiting requests"),
                }.get(error, self.tr("تعذر جلب الطقس؛ يرجى المحاولة لاحقًا", "Weather could not be retrieved; please try later"))
                self.speak(message)
                return
            # Freeze both presentations together: reopening never refetches or
            # reformats against a different date, location, units or detail level.
            formatter = self.formatter()
            name, air = self.location_name(), self.service.air_data()
            message = formatter.format(data, selected, name, air, stale=stale)
            if message != formatter.tr("بيانات التقرير المطلوب غير متاحة", "The requested report data are unavailable"):
                self.last_success_text = formatter.format(data, selected, name, air, copyable=True, stale=stale)
            if text:
                message = formatter.format(data, selected, name, air, copyable=True, stale=stale)
            if text: self._show(message)
            else: self.speak(message)
        self.service.request(selected, ready, lambda: self.speak(self.tr("يُرجى الانتظار", "Please wait")), force)

    def _show(self, message):
        WeatherTextDialog.show(gui.mainFrame, self.tr("معلومات الطقس", "Weather information"), message)
        dialog = WeatherTextDialog._instance
        if not hasattr(dialog, "weather_source_button"):
            button = dialog.weather_source_button = wx.Button(dialog, label=self.tr("مصدر البيانات والترخيص", "Data source and licence"))
            dialog.GetSizer().Add(button, 0, wx.ALL, 12)
            button.Bind(wx.EVT_BUTTON, lambda event: wx.MessageBox(SOURCE_LINKS + "\nCAMS: " + AIR_LINK, self.tr("المصدر والترخيص", "Source and licence"), wx.OK, dialog))
            dialog.Layout()

    def show(self):
        if self.closed: return
        if WeatherTextDialog._instance is not None:
            self._show("")  # The existing dialog retains its original text.
        elif self.last_success_text is not None:
            self._show(self.last_success_text)
        else:
            self.speak(self.tr("لا توجد معلومات طقس سابقة؛ اطلب تقريرًا أولًا", "No previous weather information; request a report first"))
    def refresh_now(self): self.select(force=True)

    def summary(self, language):
        if not self.service.enabled or not self.service.settings.include_in_daily_info: return ""
        entry = self.service.usable("current")
        if not entry:
            self.service.refresh()
            return ""
        formatter = WeatherFormatter(deepcopy(self.service.settings), language,
            self.zones.get_timezone(self.service.location.timezone_id), datetime.now(timezone.utc))
        return formatter.format(entry.data, "current", self.location_name(language), self.service.air_data())

    def close(self):
        if self.closed: return
        self.closed = True
        self.cancel()
        self.presses.close()
        if self.timer: self.timer.Stop()
        self.unsubscribe()
        self.service.close()
        if WeatherTextDialog._instance: WeatherTextDialog._instance.Close()
        if self.menu_item is not None:
            gui.mainFrame.sysTrayIcon.toolsMenu.DestroyItem(self.menu_item)
            self.menu_item = None
