"""Read Open-Meteo for explicit public test coordinates, never personal settings."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build/awqati/globalPlugins"))
from awqati.domain import Location
from awqati.domain.weather import WeatherSettings
from awqati.infrastructure.weather_provider import OpenMeteoProvider, WeatherError
from awqati.infrastructure.timezone_provider import BundledTimezoneProvider
from awqati.application.weather_formatters import WeatherFormatter

def main():
    out = ROOT / "docs/weather_801"
    out.mkdir(exist_ok=True)
    zones = BundledTimezoneProvider()
    provider = OpenMeteoProvider(zones)
    settings = WeatherSettings(enabled=True, detail="detailed", future_days=6)
    settings.current = dict.fromkeys(settings.current, True)
    settings.today = dict.fromkeys(settings.today, True)
    settings.future = dict.fromkeys(settings.future, True)
    location = Location("public-test", "Riyadh public test", 24.7136, 46.6753, "Asia/Riyadh")
    result = dict(checkedAt=datetime.now(timezone.utc).isoformat(), location="public Riyadh fixture, not user settings", weather=False, air=False)
    try:
        data = provider.fetch(location, settings)
        result.update(weather=True, currentFields=sorted(data.current.values) if data.current else [], days=len(data.daily), hours=len(data.hourly))
    except WeatherError as error: result["weatherError"] = error.kind
    air = None
    try:
        air = provider.fetch_air(location)
        result.update(air=True, airFields=sorted(air.values))
    except WeatherError as error: result["airError"] = error.kind
    if result["weather"]:
        for lang in ("ar", "en"):
            formatter = WeatherFormatter(settings, lang, zones.get_timezone(location.timezone_id), datetime.now(timezone.utc))
            reports = [formatter.format(data, report, location.name, air, copyable=True) for report in ("current", "today", "future")]
            (out / f"live_reports_{lang}.txt").write_text("\n\n---\n\n".join(reports), "utf-8")
    other = Location("public-test-london", "London public test", 51.5074, -0.1278, "Europe/London")
    try:
        second = provider.fetch(other, settings)
        result["secondLocation"] = dict(name="London public fixture", success=True,
            days=len(second.daily), hours=len(second.hourly), currentFields=sorted(second.current.values) if second.current else [])
    except WeatherError as error:
        result["secondLocation"] = dict(name="London public fixture", success=False, error=error.kind)
    result["stableSha256"] = hashlib.sha256((ROOT / "dist/awqati-8.0.0.nvda-addon").read_bytes()).hexdigest()
    (out / "live_connection.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), "utf-8")
    print(json.dumps(result, ensure_ascii=True))

if __name__ == "__main__": main()
