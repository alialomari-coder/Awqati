"""Weather values in canonical SI units; no network or NVDA dependencies."""
from dataclasses import dataclass, field
from datetime import datetime

BASE_CURRENT = {"weather_code", "temperature_2m", "is_day", "wind_speed_10m", "wind_direction_10m"}
BASE_HOURLY = {"is_day", "temperature_2m", "weather_code", "precipitation_probability", "wind_speed_10m"}
BASE_DAILY = {"weather_code", "temperature_2m_max", "temperature_2m_min", "precipitation_probability_max"}


class WeatherError(Exception):
    def __init__(self, kind="network", retry_after=0):
        super().__init__(kind)
        self.kind, self.retry_after = kind, retry_after


def requested_fields(settings):
    current = BASE_CURRENT | {k for k, v in settings.current.items() if v and k != "us_aqi"}
    daily = BASE_DAILY | {k for group in (settings.today, settings.future) for k, v in group.items() if v}
    if "wind_speed_10m_max" in daily:
        daily.add("wind_direction_10m_dominant")
    return tuple(sorted(current)), tuple(sorted(BASE_HOURLY)), tuple(sorted(daily))

CURRENT_OPTIONS = {
    "apparent_temperature": True,
    "relative_humidity_2m": True, "wind_gusts_10m": True,
    "pressure_msl": False, "visibility": False, "cloud_cover": False,
    "precipitation": False, "uv_index": False, "us_aqi": False,
}
DAILY_OPTIONS = {"precipitation_sum": True, "wind_speed_10m_max": True,
                 "wind_gusts_10m_max": False, "uv_index_max": False}
UNIT_CHOICES = {
    "temperature": ("celsius", "fahrenheit", "kelvin"),
    "wind": ("kmh", "ms", "mph", "knots"),
    "pressure": ("hpa", "mbar", "mmhg", "inhg"),
    "visibility": ("km", "miles"), "precipitation": ("mm", "inches"),
}
METRIC = {key: values[0] for key, values in UNIT_CHOICES.items()}
IMPERIAL = dict(temperature="fahrenheit", wind="mph", pressure="inhg",
                visibility="miles", precipitation="inches")


@dataclass(slots=True)
class WeatherSettings:
    enabled: bool = False
    detail: str = "brief"
    refresh_minutes: int = 30
    include_in_daily_info: bool = False
    current: dict = field(default_factory=lambda: dict(CURRENT_OPTIONS))
    today: dict = field(default_factory=lambda: dict(DAILY_OPTIONS))
    future: dict = field(default_factory=lambda: dict(DAILY_OPTIONS))
    unit_system: str = "metric"
    custom_units: dict = field(default_factory=lambda: dict(METRIC))
    future_days: int = 2
    upcoming_hours: int = 6
    hourly_periods: bool = True

    def validate(self):
        for value in (self.enabled, self.include_in_daily_info, self.hourly_periods):
            if type(value) is not bool:
                raise ValueError("weather flags must be boolean")
        if self.detail not in ("brief", "detailed") or self.unit_system not in ("metric", "imperial", "custom"):
            raise ValueError("invalid weather choice")
        for value, allowed in ((self.refresh_minutes, (15, 30, 60)),
                               (self.future_days, range(2, 7)), (self.upcoming_hours, (3, 6, 12))):
            if type(value) is not int or value not in allowed:
                raise ValueError("invalid weather horizon or refresh interval")
        for value, defaults in ((self.current, CURRENT_OPTIONS), (self.today, DAILY_OPTIONS), (self.future, DAILY_OPTIONS)):
            if not isinstance(value, dict) or value.keys() != defaults.keys() or any(type(v) is not bool for v in value.values()):
                raise ValueError("invalid weather information choices")
        if not isinstance(self.custom_units, dict) or self.custom_units.keys() != UNIT_CHOICES.keys():
            raise ValueError("invalid weather units")
        if any(self.custom_units[k] not in values for k, values in UNIT_CHOICES.items()):
            raise ValueError("unknown weather unit")


@dataclass(frozen=True)
class WeatherPeriod:
    time: datetime
    values: dict
    interval: int = 0


@dataclass(frozen=True)
class WeatherSnapshot:
    current: WeatherPeriod | None
    hourly: tuple
    daily: tuple


# WMO codes: preserve intensity and freezing precipitation distinctions.
CODES = {
    0: ("صافٍ", "clear"), 1: ("صافٍ غالبًا", "mainly clear"),
    2: ("غائم جزئيًا", "partly cloudy"), 3: ("غائم", "overcast"),
    45: ("ضباب", "fog"), 48: ("ضباب مع صقيع", "depositing rime fog"),
    51: ("رذاذ خفيف", "light drizzle"), 53: ("رذاذ متوسط", "moderate drizzle"),
    55: ("رذاذ كثيف", "dense drizzle"), 56: ("رذاذ متجمد خفيف", "light freezing drizzle"),
    57: ("رذاذ متجمد كثيف", "dense freezing drizzle"),
    61: ("أمطار خفيفة", "light rain"), 63: ("أمطار متوسطة", "moderate rain"),
    65: ("أمطار غزيرة", "heavy rain"), 66: ("أمطار متجمدة خفيفة", "light freezing rain"),
    67: ("أمطار متجمدة غزيرة", "heavy freezing rain"),
    71: ("ثلوج خفيفة", "light snow"), 73: ("ثلوج متوسطة", "moderate snow"),
    75: ("ثلوج كثيفة", "heavy snow"), 77: ("حبيبات ثلج", "snow grains"),
    80: ("زخات مطر خفيفة", "light rain showers"), 81: ("زخات مطر متوسطة", "moderate rain showers"),
    82: ("زخات مطر عنيفة", "violent rain showers"),
    85: ("زخات ثلج خفيفة", "light snow showers"), 86: ("زخات ثلج كثيفة", "heavy snow showers"),
    95: ("عواصف رعدية", "thunderstorms"), 96: ("عواصف رعدية مع برد خفيف", "thunderstorms with light hail"),
    99: ("عواصف رعدية مع برد كثيف", "thunderstorms with heavy hail"),
}


def description(code, arabic=False, is_day=None):
    # Missing daylight metadata and daily aggregates retain neutral descriptions.
    if is_day == 1 and code in (0, 1):
        return (("مشمس", "sunny") if code == 0 else ("مشمس غالبًا", "mainly sunny"))[0 if arabic else 1]
    return CODES.get(code, ("حالة جوية غير معروفة", "unknown weather condition"))[0 if arabic else 1]


def family(code):
    if code in (0, 1): return "clear"
    if code in (2, 3): return "cloud"
    if code in (45, 48): return "fog"
    if code in (95, 96, 99): return "storm"
    return "precipitation" if code in CODES else "unknown"
