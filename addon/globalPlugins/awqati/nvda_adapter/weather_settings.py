"""Native keyboard-accessible weather editors; mutate only the settings draft."""
from copy import deepcopy
import wx
import languageHandler
from ..domain.weather import UNIT_CHOICES
from ..application.weather_formatters import UNITS


def tr(ar, en): return ar if languageHandler.getLanguage().startswith("ar") else en


LABELS = {
    "apparent_temperature": ("درجة الحرارة المحسوسة", "Feels-like temperature"),
    "relative_humidity_2m": ("الرطوبة", "Humidity"), "wind_gusts_10m": ("هبات الرياح", "Wind gusts"),
    "pressure_msl": ("ضغط مستوى البحر", "Sea-level pressure"), "visibility": ("الرؤية", "Visibility"),
    "cloud_cover": ("الغطاء السحابي", "Cloud cover"), "precipitation": ("الهطول", "Precipitation"),
    "uv_index": ("مؤشر الأشعة فوق البنفسجية", "UV index"), "us_aqi": ("مؤشر جودة الهواء الأمريكي؛ طلب مستقل", "U.S. air quality index; separate request"),
    "precipitation_sum": ("كمية الهطول", "Precipitation amount"),
    "wind_speed_10m_max": ("أقصى سرعة رياح", "Maximum wind speed"),
    "wind_gusts_10m_max": ("هبات الرياح", "Wind gusts"), "uv_index_max": ("أقصى مؤشر للأشعة فوق البنفسجية", "Maximum UV index"),
}


def checkbox(parent, sizer, label, value, change):
    control = wx.CheckBox(parent, label=label)
    control.SetValue(value)
    control.Bind(wx.EVT_CHECKBOX, lambda event: change(control.GetValue()))
    sizer.Add(control, 0, wx.ALL, 6)
    return control


def choice(parent, sizer, label, values, labels, value, change):
    sizer.Add(wx.StaticText(parent, label=label), 0, wx.LEFT | wx.TOP, 6)
    control = wx.Choice(parent, choices=labels, name=label)
    control.SetSelection(values.index(value))
    control.Bind(wx.EVT_CHOICE, lambda event: change(values[control.GetSelection()]))
    sizer.Add(control, 0, wx.ALL | wx.EXPAND, 6)
    return control


class InformationDialog(wx.Dialog):
    def __init__(self, parent, settings):
        super().__init__(parent, title=tr("تخصيص معلومات الطقس", "Customize weather information"))
        self.values = {key: deepcopy(getattr(settings, key)) for key in ("current", "today", "future")}
        self.sizer = wx.BoxSizer(wx.VERTICAL)
        self.sizer.Add(wx.StaticText(self, label=tr("هذه الخيارات توسع التقرير المفصل؛ المعلومات الأساسية ثابتة.", "These choices extend detailed reports; core information is fixed.")), 0, wx.ALL, 8)
        self.category = choice(self, self.sizer, tr("فئة المعلومات", "Information category"),
            ("current", "today", "future"), [tr("الحالة الحالية", "Current weather"), tr("توقعات اليوم", "Today's forecast"), tr("توقعات الأيام القادمة", "Coming days forecast")], "current", self.select)
        self.body = wx.BoxSizer(wx.VERTICAL)
        self.sizer.Add(self.body, 1, wx.EXPAND)
        self.pages = {}
        for key, values in self.values.items():
            panel = wx.Panel(self)
            content = wx.BoxSizer(wx.VERTICAL)
            for field, enabled in values.items():
                checkbox(panel, content, tr(*LABELS[field]), enabled,
                         lambda value, field=field, values=values: values.__setitem__(field, value))
            panel.SetSizer(content)
            self.pages[key] = panel
            self.body.Add(panel, 1, wx.EXPAND)
        self.sizer.Add(self.CreateButtonSizer(wx.OK | wx.CANCEL), 0, wx.ALL | wx.ALIGN_RIGHT, 8)
        self.SetSizer(self.sizer)
        self.select("current")
        self.category.SetFocus()

    def select(self, key):
        for name, panel in self.pages.items(): panel.Show(name == key)
        self.Layout()
        self.Fit()


class UnitsDialog(wx.Dialog):
    def __init__(self, parent, units):
        super().__init__(parent, title=tr("تخصيص الوحدات", "Customize units"))
        self.values = dict(units)
        sizer = wx.BoxSizer(wx.VERTICAL)
        labels = {"temperature": ("الحرارة", "Temperature"), "wind": ("سرعة الرياح", "Wind speed"),
                  "pressure": ("الضغط الجوي", "Pressure"), "visibility": ("المسافات والرؤية", "Distance and visibility"), "precipitation": ("الهطول", "Precipitation")}
        for key, values in UNIT_CHOICES.items():
            choice(self, sizer, tr(*labels[key]), values, [tr(*UNITS[v]) for v in values], self.values[key],
                   lambda value, key=key: self.values.__setitem__(key, value))
        sizer.Add(self.CreateButtonSizer(wx.OK | wx.CANCEL), 0, wx.ALL | wx.ALIGN_RIGHT, 8)
        self.SetSizerAndFit(sizer)


class WeatherSettingsPanel(wx.Panel):
    def __init__(self, parent, settings, location, control):
        super().__init__(parent)
        self.settings, self.control = settings, control
        outer = wx.BoxSizer(wx.VERTICAL)
        def group(ar, en):
            box = wx.StaticBoxSizer(wx.VERTICAL, self, tr(ar, en))
            outer.Add(box, 0, wx.ALL | wx.EXPAND, 6)
            return box
        general = group("الإعدادات العامة", "General settings")
        self.enabled = checkbox(self, general, tr("تمكين خدمة الطقس", "Enable weather service"), settings.enabled, self.enable)
        general.Add(wx.StaticText(self, label=tr("عند تمكين الطقس تُرسل إحداثيات موقع أوقاتي والمنطقة الزمنية وعنوان IP إلى Open-Meteo. لا يُرسل اسمك أو إعدادات الصلاة.", "Enabling weather sends Awqati coordinates, time zone and IP address to Open-Meteo. Your name and prayer settings are not sent.")), 0, wx.ALL, 6)
        stored = location()
        general.Add(wx.StaticText(self, label=tr("الموقع المعتمد: ", "Assigned location: ") + (stored.location.name if stored else tr("لم يحدد", "Not assigned"))), 0, wx.ALL, 6)
        self.dependent = []
        def select(sizer, ar, en, key, values, labels):
            widget = choice(self, sizer, tr(ar, en), values, labels, getattr(settings, key), lambda value: setattr(settings, key, value))
            self.dependent.append(widget)
            return widget
        select(general, "مستوى التفاصيل", "Detail level", "detail", ("brief", "detailed"), [tr("مختصر", "Brief"), tr("مفصل", "Detailed")])
        select(general, "فترة التحديث التلقائي بالدقائق", "Automatic refresh in minutes", "refresh_minutes", (15, 30, 60), ["15", "30", "60"])
        self.refresh = wx.Button(self, label=tr("تحديث الآن", "Refresh now"))
        self.refresh.Bind(wx.EVT_BUTTON, self.refresh_now)
        general.Add(self.refresh, 0, wx.ALL, 6)
        self.dependent.append(self.refresh)
        general.Add(wx.StaticText(self, label=tr("التحديث يستخدم الإعدادات المحفوظة؛ طبّق التغييرات أولًا.", "Refresh uses saved settings; apply changes first.")), 0, wx.ALL, 6)
        self.dependent.append(checkbox(self, general, tr("تضمين أحوال الطقس في معلومات اليوم", "Include weather conditions in daily information"), settings.include_in_daily_info, lambda value: setattr(settings, "include_in_daily_info", value)))
        info = group("المعلومات المعروضة", "Displayed information")
        customize = wx.Button(self, label=tr("تخصيص معلومات الطقس", "Customize weather information"))
        customize.Bind(wx.EVT_BUTTON, self.information)
        info.Add(customize, 0, wx.ALL, 6)
        self.dependent.append(customize)
        units = group("وحدات القياس", "Measurement units")
        self.system = choice(self, units, tr("نظام وحدات القياس", "Unit system"), ("metric", "imperial", "custom"),
            [tr("متري", "Metric"), tr("إمبراطوري", "Imperial"), tr("مخصص", "Custom")], settings.unit_system, self.unit_system)
        self.dependent.append(self.system)
        self.custom_units = wx.Button(self, label=tr("تخصيص الوحدات", "Customize units"))
        self.custom_units.Bind(wx.EVT_BUTTON, self.units)
        units.Add(self.custom_units, 0, wx.ALL, 6)
        forecast = group("التوقعات", "Forecasts")
        select(forecast, "عدد الأيام القادمة", "Number of future days", "future_days", tuple(range(2, 7)), [str(i) for i in range(2, 7)])
        select(forecast, "الساعات القادمة", "Upcoming hours", "upcoming_hours", (3, 6, 12), ["3", "6", "12"])
        self.dependent.append(checkbox(self, forecast, tr("عرض الفترات الساعية في التقرير المفصل", "Include hourly periods in detailed report"), settings.hourly_periods, lambda value: setattr(settings, "hourly_periods", value)))
        self.SetSizer(outer)
        self.enable(settings.enabled)

    def enable(self, value):
        self.settings.enabled = value
        for widget in self.dependent: widget.Enable(value)
        self.custom_units.Enable(value and self.settings.unit_system == "custom")

    def unit_system(self, value):
        self.settings.unit_system = value
        self.custom_units.Enable(self.settings.enabled and value == "custom")

    def refresh_now(self, event):
        if self.control: self.control.refresh_now()

    def information(self, event):
        dialog = InformationDialog(self, self.settings)
        try:
            if dialog.ShowModal() == wx.ID_OK:
                for key, values in dialog.values.items(): setattr(self.settings, key, values)
        finally: dialog.Destroy()

    def units(self, event):
        dialog = UnitsDialog(self, self.settings.custom_units)
        try:
            if dialog.ShowModal() == wx.ID_OK: self.settings.custom_units = dict(dialog.values)
        finally: dialog.Destroy()
