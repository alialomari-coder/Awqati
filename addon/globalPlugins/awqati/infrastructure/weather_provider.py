"""Bounded HTTPS Open-Meteo client. Invoked only by weather worker threads."""
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
import json
import math
import socket
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from ..domain.weather import WeatherPeriod, WeatherSnapshot, WeatherError, requested_fields

MAX_BYTES = 2 * 1024 * 1024


def retry_seconds(value, now=None):
    try:
        return max(0, int(value))
    except (ValueError, TypeError):
        try:
            return max(0, parsedate_to_datetime(value).timestamp() - (time.time() if now is None else now))
        except (TypeError, ValueError, OverflowError):
            return 60


class OpenMeteoProvider:
    def __init__(self, zones, opener=urlopen):
        self.zones, self.opener = zones, opener

    def _get(self, endpoint, params):
        url = endpoint + "?" + urlencode(params)
        request = Request(url, headers={"User-Agent": "Awqati-Weather/1", "Accept": "application/json"})
        try:
            with self.opener(request, timeout=10) as response:
                if urlparse(response.geturl()).scheme != "https":
                    raise WeatherError("invalid")
                length = response.headers.get("Content-Length")
                if length and int(length) > MAX_BYTES:
                    raise WeatherError("oversize")
                payload = response.read(MAX_BYTES + 1)
                if len(payload) > MAX_BYTES:
                    raise WeatherError("oversize")
            data = json.loads(payload, parse_constant=lambda _: None)
            if not isinstance(data, dict) or data.get("error"):
                raise WeatherError("invalid")
            return data
        except HTTPError as error:
            kind = "rate" if error.code == 429 else "server" if error.code >= 500 else "request"
            raise WeatherError(kind, retry_seconds(error.headers.get("Retry-After")) if error.code == 429 else 0) from None
        except (URLError, TimeoutError, socket.timeout, OSError):
            raise WeatherError("network") from None
        except (ValueError, TypeError, UnicodeError, OverflowError):
            raise WeatherError("invalid") from None

    @staticmethod
    def _params(location):
        return dict(latitude=location.latitude, longitude=location.longitude,
                    timezone=location.timezone_id, timeformat="unixtime")

    def fetch(self, location, settings):
        current, hourly, daily = requested_fields(settings)
        params = self._params(location)
        params.update(current=",".join(current), hourly=",".join(hourly), daily=",".join(daily),
                      temperature_unit="celsius", wind_speed_unit="ms", precipitation_unit="mm",
                      forecast_days=settings.future_days + 1)
        return parse_weather(self._get("https://api.open-meteo.com/v1/forecast", params),
                             self.zones.get_timezone(location.timezone_id))

    def fetch_air(self, location):
        params = self._params(location)
        params.update(current="us_aqi", forecast_days=1)
        data = self._get("https://air-quality-api.open-meteo.com/v1/air-quality", params)
        period = _current(data, self.zones.get_timezone(location.timezone_id))
        if not period or "us_aqi" not in period.values:
            raise WeatherError("invalid")
        return period


def _number(value, key):
    if type(value) not in (float, int) or not math.isfinite(value): return None
    if key == "is_day" and value not in (0, 1): return None
    if key in ("weather_code",) and (value != int(value) or not 0 <= value <= 999): return None
    if ("probability" in key or key in ("relative_humidity_2m", "cloud_cover")) and not 0 <= value <= 100: return None
    if "direction" in key and not 0 <= value <= 360: return None
    if "temperature" in key and not -150 <= value <= 100: return None
    if not ("temperature" in key or key == "weather_code") and value < 0: return None
    # Reject finite but corrupt magnitudes before unit conversion/rounding on
    # the UI thread. These broad bounds include extreme plausible model data.
    maximum = 200 if key.startswith(("wind_speed", "wind_gusts")) else 2000 if key == "pressure_msl" else 1000000 if key == "visibility" else 10000 if "precipitation" in key or key == "us_aqi" else 100 if key.startswith("uv_index") else None
    if maximum is not None and value > maximum: return None
    return value


def _unit(key):
    if key == "is_day": return ("",)
    if "temperature" in key: return ("°C",)
    if "wind_speed" in key or "wind_gusts" in key: return ("m/s",)
    if "direction" in key: return ("°",)
    if "probability" in key or key in ("relative_humidity_2m", "cloud_cover"): return ("%",)
    if key == "pressure_msl": return ("hPa",)
    if key == "visibility": return ("m",)
    if "precipitation" in key: return ("mm",)
    if key == "weather_code": return ("wmo code",)
    if key.startswith("uv_index"): return ("",)
    if key == "us_aqi": return ("USAQI", "US AQI")
    return ()


def _time(value, zone):
    if type(value) not in (int, float) or not math.isfinite(value): return None
    try: return datetime.fromtimestamp(value, timezone.utc).astimezone(zone)
    except (ValueError, OverflowError, OSError): return None


def _values(raw, units):
    result = {}
    for key, value in raw.items():
        if units.get(key) in _unit(key):
            number = _number(value, key)
            if number is not None: result[key] = number
    return result


def _current(data, zone):
    raw, units = data.get("current", {}), data.get("current_units", {})
    if not isinstance(raw, dict) or not isinstance(units, dict): return None
    stamp = _time(raw.get("time"), zone) if units.get("time") == "unixtime" else None
    interval = raw.get("interval", 0)
    if units.get("interval") != "seconds" or type(interval) is not int or not 0 < interval <= 86400: interval = 0
    return WeatherPeriod(stamp, _values(raw, units), interval) if stamp else None


def _series(data, name, zone):
    raw, units = data.get(name, {}), data.get(name + "_units", {})
    if not isinstance(raw, dict) or not isinstance(units, dict): return ()
    times = raw.get("time", [])
    if not isinstance(times, list) or units.get("time") != "unixtime" or len(times) > 400: return ()
    periods = []
    last = float("-inf")
    for index, value in enumerate(times):
        stamp = _time(value, zone)
        if stamp is None or value <= last: continue
        last = value
        # Never relabel a fixed-offset daily bucket crossing a DST boundary.
        if name == "daily" and (stamp.hour or stamp.minute or stamp.second): continue
        if name == "daily" and index + 1 < len(times):
            end = _time(times[index + 1], zone)
            if end is None or end.hour or end.minute or end.second or end.date() != stamp.date() + timedelta(days=1):
                continue
        values = {k: v[index] for k, v in raw.items() if k != "time" and isinstance(v, list) and len(v) == len(times)}
        periods.append(WeatherPeriod(stamp, _values(values, units)))
    return tuple(periods)


def parse_weather(data, zone):
    if not isinstance(data, dict): raise WeatherError("invalid")
    current = _current(data, zone)
    hourly, daily = _series(data, "hourly", zone), _series(data, "daily", zone)
    if not ((current and ({"weather_code", "temperature_2m"} & current.values.keys())) or hourly or daily):
        raise WeatherError("invalid")
    return WeatherSnapshot(current, hourly, daily)
