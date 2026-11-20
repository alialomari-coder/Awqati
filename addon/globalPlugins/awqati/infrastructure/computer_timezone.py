"""Windows computer zone, independent of the prayer calculation location.

Windows IDs use the bundled CLDR mapping (Babel build dependency).
DynamicDaylightTimeDisabled explicitly selects the computer's fixed offset.
"""
from datetime import datetime
import json
from time import monotonic
from pathlib import Path


class ComputerTimezone:
    def __init__(self, zones):
        self.zones = zones
        self._cached = None
        self._cached_at = 0
        path = Path(__file__).resolve().parents[1] / "data/timezones/windows_zones.json"
        self.mapping = json.loads(path.read_text(encoding="utf-8"))

    def __call__(self):
        if self._cached is not None and monotonic() - self._cached_at < 1:
            return self._cached
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\TimeZoneInformation") as key:
            name = winreg.QueryValueEx(key, "TimeZoneKeyName")[0].rstrip("\0")
            try:
                disabled = winreg.QueryValueEx(key, "DynamicDaylightTimeDisabled")[0]
            except FileNotFoundError:
                disabled = False
        if disabled:
            zone = datetime.now().astimezone().tzinfo
        elif name not in self.mapping:
            raise ValueError("Windows time zone is not in the bundled CLDR mapping: " + name)
        else:
            zone = self.zones.get_timezone(self.mapping[name])
        self._cached, self._cached_at = zone, monotonic()
        return zone
