"""Independent weather cache and workers; all state changes run on the UI dispatcher."""
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
import random
import threading
import time

from ..domain.weather import WeatherError, requested_fields


@dataclass
class CacheEntry:
    data: object
    fetched: float


class WeatherService:
    def __init__(self, provider, dispatch, clock=time.monotonic,
                 utcnow=lambda: datetime.now(timezone.utc), launch=None):
        self.provider, self.dispatch, self.clock, self.utcnow = provider, dispatch, clock, utcnow
        self.launch = launch or (lambda work: threading.Thread(target=work, name="Awqati weather", daemon=True).start())
        self.settings = None
        self.location = None
        self.generation = 0
        self.air_generation = 0
        self.cache = self.air = None
        self.busy = {"weather": False, "air": False}
        self.blocked = {"weather": 0, "air": 0}
        self.last_attempt = {"weather": float("-inf"), "air": float("-inf")}
        self.failures = {"weather": 0, "air": 0}
        self.errors = {"weather": None, "air": None}
        self.pending = None
        self.closed = False
        self._key = None
        self._air_enabled = False
        self.wait_announced = False

    @property
    def enabled(self):
        return not self.closed and self.settings is not None and self.settings.enabled and self.location is not None

    def configure(self, settings, location):
        key = None if not settings.enabled or location is None else (
            location.latitude, location.longitude, location.timezone_id,
            requested_fields(settings), settings.future_days)
        air_enabled = bool(settings.enabled and settings.current["us_aqi"])
        old_location = self._key[:3] if self._key else None
        new_location = key[:3] if key else None
        if key != self._key:
            self.generation += 1
            self.pending = None
            self.wait_announced = False
            # Old workers retain their busy slot until they finish. This prevents
            # an unbounded number of threads while settings change repeatedly.
            self.cache = None
        if old_location != new_location or air_enabled != self._air_enabled:
            self.air_generation += 1
            self.air = None
        self._key = key
        self._air_enabled = air_enabled
        self.settings, self.location = deepcopy(settings), location
        if not self.enabled:
            self.cache = self.air = None

    def cancel_speech(self):
        self.pending = None

    def fresh(self, kind="weather"):
        entry = self.cache if kind == "weather" else self.air
        ttl = self.settings.refresh_minutes * 60 if kind == "weather" else 3600
        return entry if entry and 0 <= self.clock() - entry.fetched < ttl else None

    def usable(self, report="current", stale=False):
        entry = self.cache if stale else self.fresh()
        if not entry or not 0 <= self.clock() - entry.fetched < 7200: return None
        data, now = entry.data, self.utcnow()
        if report == "current":
            if not data.current or not ({"weather_code", "temperature_2m"} & data.current.values.keys()): return None
            age = now.timestamp() - data.current.time.timestamp()
            if not -900 <= age < 7200: return None
        else:
            if report == "future" and not stale and self._needs_new_day(): return None
            day = now.astimezone(self.provider.zones.get_timezone(self.location.timezone_id)).date()
            dates = {p.time.date() for p in data.daily if p.values}
            if report == "today" and day not in dates and not any(p.time.timestamp() >= now.timestamp() for p in data.hourly): return None
            if report == "future" and not any(day + timedelta(days=i) in dates for i in range(1, self.settings.future_days + 1)): return None
        return entry

    def _needs_new_day(self):
        if not self.cache or not self.cache.data.daily: return False
        day = self.utcnow().astimezone(self.provider.zones.get_timezone(self.location.timezone_id)).date()
        dates = [period.time.date() for period in self.cache.data.daily]
        return min(dates) < day and max(dates) < day + timedelta(days=self.settings.future_days)

    def air_data(self):
        entry = self.fresh("air") if self._air_enabled else None
        if entry and -900 <= self.utcnow().timestamp() - entry.data.time.timestamp() < 7200:
            return entry.data
        return None

    def request(self, report, callback, waiting, force=False):
        self.pending = None
        if not self.enabled:
            callback(None, "disabled" if self.settings and not self.settings.enabled else "location", False)
            return
        ready = self.usable(report)
        if ready and not force:
            callback(ready.data, None, False)
            self.refresh()
            return
        # Forced requests must observe a new successful fetch, even inside TTL.
        self.pending = (report, callback, force, self.cache)
        will_fetch = self.busy["weather"] or self._can_start("weather", force)
        if not self.busy["weather"]: self.wait_announced = False
        if will_fetch and not self.wait_announced:
            self.wait_announced = True
            waiting()
        self.refresh(force)
        if not self.busy["weather"] and not self.busy["air"]:
            self._deliver(self.errors["weather"] or "unavailable")

    def _can_start(self, kind, force=False):
        return (self.enabled and not self.busy[kind] and self.clock() >= self.blocked[kind]
                and self.clock() - self.last_attempt[kind] >= 60
                and (force or self.fresh(kind) is None or (kind == "weather" and self._needs_new_day()))
                and (kind != "air" or self._air_enabled))

    def refresh(self, force=False):
        if not self.enabled: return
        # Start both before any completion can be delivered on the UI thread.
        for kind in ("air", "weather"):
            if self._can_start(kind, force): self._start(kind)

    def _start(self, kind):
        self.busy[kind] = True
        self.last_attempt[kind] = self.clock()
        generation = self.air_generation if kind == "air" else self.generation
        location, settings = self.location, deepcopy(self.settings)
        def work():
            data, error = None, None
            try:
                data = self.provider.fetch_air(location) if kind == "air" else self.provider.fetch(location, settings)
            except WeatherError as failure: error = failure
            except Exception: error = WeatherError("invalid")
            self.dispatch(self._finish, kind, generation, data, error)
        self.launch(work)

    def _finish(self, kind, generation, data, error):
        self.busy[kind] = False
        # Source backoff survives changes of location, options and enable state.
        if error:
            self.errors[kind] = error.kind
            self.failures[kind] += 1
            delay = (60, 300, 900)[min(self.failures[kind] - 1, 2)]
            if error.kind == "rate": delay = max(60, error.retry_after)
            elif error.kind in ("request", "invalid", "oversize"): delay = max(900, self.settings.refresh_minutes * 60)
            self.blocked[kind] = self.clock() + delay
        else:
            self.failures[kind] = 0
            self.errors[kind] = None
        expected_generation = self.air_generation if kind == "air" else self.generation
        if self.closed or generation != expected_generation or not self.enabled:
            if self.enabled:
                self.refresh()
                if not any(self.busy.values()): self._deliver("unavailable")
            return
        if not error:
            entry = CacheEntry(data, self.clock())
            if kind == "air": self.air = entry
            else: self.cache = entry
        if not self.busy["weather"] and not self.busy["air"]:
            self._deliver(error.kind if kind == "weather" and error else None)

    def _deliver(self, error=None):
        if self.pending is None: return
        report, callback, force, previous_cache = self.pending
        self.pending = None
        entry = self.usable(report)
        if force:
            failure = error or self.errors["weather"]
            if failure or entry is None or self.cache is previous_cache:
                callback(None, failure or "unavailable", False)
            else:
                callback(entry.data, None, False)
            return
        stale = bool(entry is not None and self.errors["weather"])
        if entry is None and self.errors["weather"]:
            entry = self.usable(report, stale=True)
            stale = entry is not None
        callback(entry.data if entry else None, error if not entry else None, stale)

    def next_tick_ms(self):
        # A light independent timer checks both TTLs and backoff. Jitter prevents
        # multiple installations from repeatedly hitting the same second.
        return int((60 + random.uniform(0, 15)) * 1000)

    def close(self):
        self.closed = True
        self.generation += 1
        self.air_generation += 1
        self.pending = None
        self.cache = self.air = None
