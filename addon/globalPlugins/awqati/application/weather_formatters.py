"""Listening-oriented Arabic/English weather reports and non-cumulative units."""
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP
from ..domain.weather import METRIC, IMPERIAL, description, family

SOURCE_LINKS = "https://open-meteo.com/\nhttps://creativecommons.org/licenses/by/4.0/"
AIR_LINK = "https://atmosphere.copernicus.eu/"


def number(value, places=0):
    rounded = Decimal(str(value)).quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)
    if not rounded: rounded = abs(rounded)
    return format(rounded, "f").rstrip("0").rstrip(".") if places else format(rounded, "f")


def convert(value, unit):
    return {
        "fahrenheit": lambda x: x * 9 / 5 + 32, "kelvin": lambda x: x + 273.15,
        "kmh": lambda x: x * 3.6, "mph": lambda x: x / .44704,
        "knots": lambda x: x / (1852 / 3600), "mmhg": lambda x: x / 1.33322387415,
        "inhg": lambda x: x / 33.8638866667, "km": lambda x: x / 1000,
        "miles": lambda x: x / 1609.344, "inches": lambda x: x / 25.4,
    }.get(unit, lambda x: x)(value)


UNITS = {
    "celsius": ("درجة مئوية", "degrees Celsius"), "fahrenheit": ("درجة فهرنهايت", "degrees Fahrenheit"),
    "kelvin": ("كلفن", "kelvin"), "kmh": ("كيلومتر في الساعة", "kilometres per hour"),
    "ms": ("متر في الثانية", "metres per second"), "mph": ("ميل في الساعة", "miles per hour"),
    "knots": ("عقدة", "knots"), "hpa": ("هكتوباسكال", "hectopascals"),
    "mbar": ("مليبار", "millibars"), "mmhg": ("ملليمتر زئبق", "millimetres of mercury"),
    "inhg": ("بوصة زئبق", "inches of mercury"), "km": ("كيلومتر", "kilometres"),
    "miles": ("ميل", "miles"), "mm": ("ملليمتر", "millimetres"), "inches": ("بوصة", "inches"),
}


class WeatherFormatter:
    def __init__(self, settings, language, zone, now):
        self.settings, self.zone = settings, zone
        self.ar = language.split("_", 1)[0].split("-", 1)[0] == "ar"
        self.now = now.astimezone(zone)
        self.detailed = settings.detail == "detailed"
        self.units = METRIC if settings.unit_system == "metric" else IMPERIAL if settings.unit_system == "imperial" else settings.custom_units

    def tr(self, ar, en): return ar if self.ar else en

    def quantity(self, value, kind):
        unit = self.units[kind]
        places = (1 if self.detailed else 0) if kind in ("temperature", "wind") else 2 if unit in ("inhg", "inches") else 1
        converted = convert(value, unit)
        text = number(converted, places)
        if kind == "precipitation" and 0 < converted < 10 ** -places:
            text = self.tr("أقل من ", "less than ") + number(10 ** -places, places)
        return text + " " + UNITS[unit][0 if self.ar else 1]

    def percent(self, value): return number(value) + self.tr(" بالمئة", " percent")

    def wind(self, values, daily=False):
        key = "wind_speed_10m_max" if daily else "wind_speed_10m"
        speed = values.get(key)
        if speed is None: return ""
        if speed < .5: return self.tr("رياح هادئة", "calm wind")
        text = self.tr("أقصى سرعة رياح ", "maximum wind ") if daily else self.tr("رياح بسرعة ", "wind at ")
        text += self.quantity(speed, "wind")
        direction = values.get("wind_direction_10m_dominant" if daily else "wind_direction_10m")
        if direction is not None:
            directions = (("شمالية", "شمالية شرقية", "شرقية", "جنوبية شرقية", "جنوبية", "جنوبية غربية", "غربية", "شمالية غربية"),
                          ("north", "northeast", "east", "southeast", "south", "southwest", "west", "northwest"))
            text += self.tr("، قادمة من جهة ", ", from ") + directions[0 if self.ar else 1][int((direction + 22.5) // 45) % 8]
        return text

    def attribution(self, air=False):
        text = self.tr("بيانات الطقس: Open-Meteo", "Weather data: Open-Meteo")
        if air: text += self.tr("؛ جودة الهواء: CAMS وOpen-Meteo", "; air quality: CAMS and Open-Meteo")
        return text + "."

    def current_parts(self, period, today=None, air=None, copyable=False):
        values, parts = period.values if period else {}, []
        if "weather_code" in values:
            parts.append(self.tr("الحالة الجوية: " if copyable else "الجو ", "Conditions: " if copyable else "Currently ")
                         + description(values["weather_code"], self.ar, values.get("is_day")))
        if "temperature_2m" in values:
            parts.append(self.tr("درجة الحرارة الحالية: " if copyable else "درجة الحرارة الحالية ", "Temperature: " if copyable else "the temperature is ")
                         + self.quantity(values["temperature_2m"], "temperature"))
        for key, ar, en in (("temperature_2m_max", "العظمى المتوقعة", "expected high"),
                            ("temperature_2m_min", "الصغرى المتوقعة", "expected low")):
            if today and key in today.values:
                value = self.quantity(today.values[key], "temperature")
                if not copyable and "temperature_2m" in values:
                    value = number(convert(today.values[key], self.units["temperature"]), 1 if self.detailed else 0)
                    value += self.tr(" كلفن", " kelvin") if self.units["temperature"] == "kelvin" else self.tr(" درجة", " degrees")
                parts.append(self.tr(ar, en) + (": " if copyable else " ") + value)
        if self.detailed:
            options = self.settings.current
            if options["apparent_temperature"] and "apparent_temperature" in values:
                parts.append(self.tr("الحرارة المحسوسة ", "feels like ") + self.quantity(values["apparent_temperature"], "temperature"))
            if self.wind(values): parts.append(self.wind(values))
            for key, ar, en, kind in (
                ("wind_gusts_10m", "هبات الرياح ", "wind gusts ", "wind"),
                ("relative_humidity_2m", "الرطوبة ", "humidity ", "percent"),
                ("pressure_msl", "الضغط الجوي عند مستوى البحر ", "sea-level pressure ", "pressure"),
                ("visibility", "الرؤية ", "visibility ", "visibility"),
                ("cloud_cover", "السحب ", "cloud cover ", "percent"),
            ):
                if options[key] and key in values:
                    value = self.percent(values[key]) if kind == "percent" else number(values[key], 1) if kind == "index" else self.quantity(values[key], kind)
                    parts.append(self.tr(ar, en) + value)
            if options["precipitation"] and "precipitation" in values and period.interval:
                parts.append(self.tr("الهطول خلال آخر ", "precipitation over the last ")
                             + number(period.interval / 60, 1) + self.tr(" دقيقة: ", " minutes: ") + self.quantity(values["precipitation"], "precipitation"))
            if options["uv_index"] and "uv_index" in values:
                parts.append(self.tr("مؤشر الأشعة فوق البنفسجية ", "UV index ") + number(values["uv_index"], 1))
            if options["us_aqi"] and air and "us_aqi" in air.values:
                value = air.values["us_aqi"]
                index = next((i for i, limit in enumerate((50, 100, 150, 200, 300)) if value <= limit), 5)
                labels = (("جيد", "متوسط", "غير صحي للفئات الحساسة", "غير صحي", "غير صحي جدًا", "خطر"),
                          ("good", "moderate", "unhealthy for sensitive groups", "unhealthy", "very unhealthy", "hazardous"))
                parts.append(self.tr("مؤشر جودة الهواء الأمريكي ", "U.S. air quality index ") + number(value) + self.tr("، ", ", ") + labels[0 if self.ar else 1][index])
        return parts

    def current(self, period, air=None, brief=False):
        separator = ". " if self.ar and self.detailed else self.tr("، و", ", ")
        return separator.join(self.current_parts(period, air=air))

    def daily(self, period, options):
        v, parts = period.values, []
        if "weather_code" in v: parts.append(description(v["weather_code"], self.ar))
        for key, ar, en in (("temperature_2m_max", "العظمى ", "high "), ("temperature_2m_min", "الصغرى ", "low ")):
            if key in v: parts.append(self.tr(ar, en) + self.quantity(v[key], "temperature"))
        if "precipitation_probability_max" in v:
            probability = v["precipitation_probability_max"]
            value = "صفر بالمئة" if self.ar and probability == 0 else self.percent(probability)
            parts.append(self.tr("أعلى احتمال لهطول الأمطار خلال إحدى ساعات اليوم المتاحة: ", "highest hourly precipitation probability ") + value)
        if self.detailed:
            if options["precipitation_sum"] and "precipitation_sum" in v:
                parts.append(self.tr("كمية الهطول اليومية المتوقعة ", "expected daily precipitation amount ") + self.quantity(v["precipitation_sum"], "precipitation"))
            if options["wind_speed_10m_max"] and self.wind(v, True): parts.append(self.wind(v, True))
            if options["wind_gusts_10m_max"] and "wind_gusts_10m_max" in v:
                parts.append(self.tr("هبات الرياح ", "wind gusts ") + self.quantity(v["wind_gusts_10m_max"], "wind"))
            if options["uv_index_max"] and "uv_index_max" in v:
                parts.append(self.tr("أقصى مؤشر للأشعة فوق البنفسجية ", "maximum UV index ") + number(v["uv_index_max"], 1))
        return ". ".join(parts)

    def time_label(self, stamp, at_hour=False):
        stamp = stamp.astimezone(self.zone)
        prefix = ""
        if stamp.date() != self.now.date():
            prefix = self.tr("غدًا ", "tomorrow ") if stamp.date() == self.now.date() + timedelta(days=1) else stamp.date().isoformat() + " "
        hour = stamp.hour % 12 or 12
        clock = str(hour) + (f":{stamp.minute:02d}" if stamp.minute else "")
        if self.ar:
            if at_hour:
                if not stamp.minute:
                    clock = ("الواحدة", "الثانية", "الثالثة", "الرابعة", "الخامسة", "السادسة",
                             "السابعة", "الثامنة", "التاسعة", "العاشرة", "الحادية عشرة", "الثانية عشرة")[hour - 1]
                prefix += "عند الساعة "
            period = "صباحًا" if stamp.hour < 12 else "ظهرًا" if stamp.hour == 12 else "عصرًا" if stamp.hour < 17 else "مساءً" if stamp.hour < 21 else "ليلًا"
        else:
            period = "AM" if stamp.hour < 12 else "PM"
        text = prefix + clock + " " + period
        # Speak the offset only where the local hour is genuinely ambiguous.
        if stamp.replace(fold=0).utcoffset() != stamp.replace(fold=1).utcoffset():
            offset = stamp.utcoffset().total_seconds() / 3600
            sign = self.tr("ناقص ", "minus ") if offset < 0 else self.tr("زائد ", "plus ")
            text += self.tr("، إزاحة UTC ", ", UTC offset ") + sign + number(abs(offset), 2) + self.tr(" ساعات", " hours")
        return text

    def range_time_label(self, stamp):
        """Natural Arabic endpoint; retain minutes and ambiguous UTC offsets."""
        if not self.ar:
            return self.time_label(stamp)
        stamp = stamp.astimezone(self.zone)
        label = self.time_label(stamp, at_hour=True)
        clock = label.split("عند الساعة ", 1)[1]
        if stamp.date() == self.now.date() + timedelta(days=1):
            for period, next_day in (("صباحًا", "من صباح الغد"), ("ظهرًا", "من ظهر الغد"),
                                     ("عصرًا", "من عصر الغد"), ("مساءً", "من مساء الغد"),
                                     ("ليلًا", "من ليل الغد")):
                if period in clock:
                    return clock.replace(period, next_day, 1)
        if stamp.date() != self.now.date():
            clock += " بتاريخ " + stamp.date().isoformat()
        return clock

    def hourly(self, snapshot, copyable=False):
        horizon = self.now.timestamp() + self.settings.upcoming_hours * 3600
        hours = [p for p in snapshot.hourly if self.now.timestamp() < p.time.timestamp() <= horizon and p.values]
        baseline = dict(hours[0].values) if hours else {}
        if snapshot.current: baseline.update(snapshot.current.values)
        changed = []
        previous = baseline
        previous_temperature_band = 0
        for p in hours:
            v = p.values
            state = ("weather_code" in v and "weather_code" in previous and family(v["weather_code"]) != family(previous["weather_code"]))
            rain = v.get("precipitation_probability", -1) >= 50 > previous.get("precipitation_probability", 100)
            difference = v.get("temperature_2m", baseline.get("temperature_2m", 0)) - baseline.get("temperature_2m", v.get("temperature_2m", 0))
            band = 1 if difference >= 5 else -1 if difference <= -5 else 0
            temp = bool(band and band != previous_temperature_band)
            previous_temperature_band = band
            wind = v.get("wind_speed_10m", 0) >= 10 > previous.get("wind_speed_10m", 10)
            if state or rain or temp or wind:
                changed.append(p)
            previous = v
        def line(p, omit_zero=False):
            v, bits = p.values, []
            if "weather_code" in v: bits.append(description(v["weather_code"], self.ar, v.get("is_day")))
            if "temperature_2m" in v: bits.append(self.quantity(v["temperature_2m"], "temperature"))
            if "precipitation_probability" in v and not omit_zero: bits.append(self.tr("احتمال هطول ", "precipitation probability ") + self.percent(v["precipitation_probability"]))
            if "wind_speed_10m" in v: bits.append(self.wind(v))
            return self.tr("", "At ") + self.time_label(p.time, at_hour=self.ar) + ": " + self.tr("، ", ", ").join(bits)
        if self.detailed and self.settings.hourly_periods:
            # Actual point-in-time samples, distributed across the full horizon.
            step = {3: 1, 6: 2, 12: 3}[self.settings.upcoming_hours] * 3600
            selected = []
            for p in hours:
                if not selected or p.time.timestamp() - selected[-1].time.timestamp() >= step:
                    selected.append(p)
            if hours and selected[-1] is not hours[-1]: selected.append(hours[-1])
            # Unknown probabilities are not zero. Check every available hour,
            # including unsampled hours, before summarizing the spoken values.
            dry = not copyable and bool(hours) and all(p.values.get("precipitation_probability") == 0 for p in hours)
            lines = [line(p, omit_zero=dry) for p in selected]
            if dry:
                lines.insert(0, self.tr("لا يُتوقع هطول أمطار خلال الفترة الممتدة من ", "No rain is expected in the available hourly readings from ")
                             + self.range_time_label(hours[0].time) + self.tr(" حتى ", " to ") + self.range_time_label(hours[-1].time))
            return (".\n" if copyable else ". ").join(lines)
        if changed: return line(changed[0])
        # Only claim stability when all required hourly values cover the horizon.
        if len(hours) == self.settings.upcoming_hours and all({"weather_code", "temperature_2m", "wind_speed_10m", "precipitation_probability"} <= p.values.keys() for p in hours) and all(k in previous for k in ("temperature_2m", "weather_code")):
            return self.tr("لا تغير ملحوظ متوقع خلال الساعات القادمة وعددها ", "No significant change expected within the next hours: ") + str(self.settings.upcoming_hours)
        return ""

    def format(self, snapshot, report, location_name, air=None, copyable=False, stale=False, summary=False):
        parts = []
        if stale: parts.append(self.tr("تعذر الاتصال؛ هذه بيانات محفوظة وقد تكون غير محدثة", "Connection failed; these cached data may be out of date"))
        if report == "current":
            today = next((p for p in snapshot.daily if p.time.date() == self.now.date()), None)
            content = self.current_parts(snapshot.current, today, air, copyable)
            if content:
                title = self.tr("أحوال الطقس في ", "Weather in ") + location_name
                if not self.detailed: title += self.tr(" اليوم", " today")
                separator = ".\n" if copyable else ". " if self.ar and self.detailed else self.tr("، و", ", ")
                parts.append(title + ("\n" if copyable else ": ") + separator.join(content))
        elif report == "today":
            period = next((p for p in snapshot.daily if p.time.date() == self.now.date()), None)
            if period and period.values:
                content = self.daily(period, self.settings.today)
                if self.ar and period.values.get("weather_code") == 0:
                    content = content.replace("صافٍ", "السماء صافية", 1)
                parts.append(self.tr("توقعات الطقس في ", "Weather forecast for ") + location_name + self.tr(" اليوم: ", " today: ") + content)
            hourly = self.hourly(snapshot, copyable)
            if hourly: parts.append(hourly)
        else:
            for offset in range(1, self.settings.future_days + 1):
                day = self.now.date() + timedelta(days=offset)
                period = next((p for p in snapshot.daily if p.time.date() == day), None)
                if period and period.values:
                    name = self.tr("غدًا", "tomorrow") if offset == 1 else self.tr("بعد غد", "the day after tomorrow") if offset == 2 else day.isoformat()
                    parts.append(name + ": " + self.daily(period, self.settings.future))
            if parts and not (stale and len(parts) == 1):
                parts.insert(1 if stale else 0, self.tr("توقعات الطقس في ", "Weather forecast for ") + location_name + self.tr(" للأيام القادمة", " for the coming days"))
        if not parts or (stale and len(parts) == 1):
            return self.tr("بيانات التقرير المطلوب غير متاحة", "The requested report data are unavailable")
        used_air = report == "current" and self.detailed and self.settings.current["us_aqi"] and air is not None and "us_aqi" in air.values
        text = (".\n" if copyable else ". ").join(parts) + "."
        if copyable:
            text += "\n\n" + self.attribution(used_air) + "\nCC BY 4.0\n" + self.tr("تقديرات نموذجية وليست قياسات محطة محلية. النص مترجم وملخص والوحدات محولة.", "Model estimates, not local station observations. Text translated and summarized; units converted.") + "\n" + SOURCE_LINKS
            if used_air: text += "\n" + AIR_LINK
        return text
