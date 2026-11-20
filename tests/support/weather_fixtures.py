"""Synthetic Open-Meteo response; safe to import in trimmed NVDA runtimes."""
from datetime import datetime, timezone, timedelta

def fixture(now, zone=timezone.utc):
    local = now.astimezone(zone)
    current = {"time": int(now.timestamp()), "interval": 900, "weather_code": 2, "temperature_2m": 22,
               "apparent_temperature": 21, "wind_speed_10m": 3.4, "wind_direction_10m": 0,
               "relative_humidity_2m": 0, "wind_gusts_10m": 7, "precipitation": .001,
               "pressure_msl": 1015, "visibility": 10000, "cloud_cover": 0, "uv_index": 0}
    units = {"time": "unixtime", "interval": "seconds", "weather_code": "wmo code", "temperature_2m": "°C", "apparent_temperature": "°C", "wind_speed_10m": "m/s", "wind_direction_10m": "°", "relative_humidity_2m": "%", "wind_gusts_10m": "m/s", "precipitation": "mm", "pressure_msl": "hPa", "visibility": "m", "cloud_cover": "%", "uv_index": ""}
    daily = {"time": [int((local.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=i)).timestamp()) for i in range(7)],
             "weather_code": [2]*7, "temperature_2m_max": [26]*7, "temperature_2m_min": [17]*7,
             "precipitation_probability_max": [0]*7, "precipitation_sum": [0]*7,
             "wind_speed_10m_max": [4]*7, "wind_gusts_10m_max": [7]*7,
             "wind_direction_10m_dominant": [0]*7, "uv_index_max": [0]*7}
    daily_units = {"time": "unixtime", "weather_code": "wmo code", "temperature_2m_max": "°C", "temperature_2m_min": "°C", "precipitation_probability_max": "%", "precipitation_sum": "mm", "wind_speed_10m_max": "m/s", "wind_gusts_10m_max": "m/s", "wind_direction_10m_dominant": "°", "uv_index_max": ""}
    hourly = {"time": [int(now.replace(minute=0, second=0, microsecond=0).timestamp()) + 3600*i for i in range(1, 14)], "weather_code": [2]*13,
              "temperature_2m": [22]*13, "precipitation_probability": [0]*13, "wind_speed_10m": [3]*13}
    hourly_units = {k: units.get(k, "%") for k in hourly}
    return dict(current=current, current_units=units, daily=daily, daily_units=daily_units, hourly=hourly, hourly_units=hourly_units)
