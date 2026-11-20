"""Four principal longitude phases (Meeus ch.49), independent of appearance.

UTC range is [1901-01-01, 2100-01-01). Historical/future modeled UT is
explicitly identified: future leap seconds and pre-UTC civil time are unknown.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone, tzinfo
from enum import Enum
import math

from .astronomy import (
    AstronomyRangeError, _require_aware, validate_astronomy_year,
    _lunar_phase_jde_tt, _tt_jd_to_utc, julian_day,
)

ALGORITHM_VERSION = "awqati-principal-phases-meeus49-v1"
_MIN = datetime(1901, 1, 1, tzinfo=timezone.utc)
_END = datetime(2100, 1, 1, tzinfo=timezone.utc)
# IERS Bulletin C leap-second history; confirmed horizon is deliberately finite.
_LEAPS = (
    (1972,1,10),(1972,7,11),(1973,1,12),(1974,1,13),(1975,1,14),
    (1976,1,15),(1977,1,16),(1978,1,17),(1979,1,18),(1980,1,19),
    (1981,7,20),(1982,7,21),(1983,7,22),(1985,7,23),(1988,1,24),
    (1990,1,25),(1991,1,26),(1992,7,27),(1993,7,28),(1994,7,29),
    (1996,1,30),(1997,7,31),(1999,1,32),(2006,1,33),(2009,1,34),
    (2012,7,35),(2015,7,36),(2017,1,37),
)
_CONFIRMED_END = datetime(2027, 1, 1, tzinfo=timezone.utc)


class PrincipalPhase(Enum):
    NEW_MOON = "newMoon"
    FIRST_QUARTER = "firstQuarter"
    FULL_MOON = "fullMoon"
    LAST_QUARTER = "lastQuarter"


@dataclass(frozen=True, slots=True)
class LunarPhaseEvent:
    phase: PrincipalPhase
    at_utc: datetime
    jde_tt: float
    time_basis: str  # utcLeapSeconds or modeledUT (proleptic UTC container)
    algorithm_version: str = ALGORITHM_VERSION

    def local_time(self, zone: tzinfo) -> datetime:
        return self.at_utc.astimezone(zone)


@dataclass(frozen=True, slots=True)
class UpcomingLunarPhases:
    requested_at_utc: datetime
    events: tuple[LunarPhaseEvent, ...]  # next of each type, in UTC order
    zone: tzinfo = timezone.utc

    @property
    def next_local(self) -> datetime | None:
        return self.next_event.local_time(self.zone) if self.next_event else None

    @property
    def next_event(self) -> LunarPhaseEvent | None:
        return self.events[0] if self.events else None

    def next_for(self, phase: PrincipalPhase) -> LunarPhaseEvent | None:
        if not isinstance(phase, PrincipalPhase):
            raise ValueError("phase must be a PrincipalPhase")
        return next((e for e in self.events if e.phase is phase), None)


def _event(k: float, phase: PrincipalPhase) -> LunarPhaseEvent:
    tt = _lunar_phase_jde_tt(k)
    civil_tt = datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(days=tt-2440587.5)
    # Select offsets using effective instants on the TT timeline.
    offset = None
    for year, month, tai in _LEAPS:
        effective_tt = datetime(year, month, 1, tzinfo=timezone.utc) + timedelta(seconds=32.184+tai)
        if civil_tt >= effective_tt:
            offset = 32.184+tai
    if offset is not None and civil_tt < _CONFIRMED_END:
        utc, basis = civil_tt-timedelta(seconds=offset), "utcLeapSeconds"
    else:
        utc, basis = _tt_jd_to_utc(tt), "modeledUT"
    return LunarPhaseEvent(phase, utc, tt, basis)


def _utc(moment: datetime) -> datetime:
    _require_aware(moment)
    utc = moment.astimezone(timezone.utc)
    validate_astronomy_year(utc.year)
    return utc


def lunar_phase_events(start: datetime, end: datetime) -> tuple[LunarPhaseEvent, ...]:
    """Events in [start,end); supports end exactly at exclusive range boundary.

    No rounded comparison, tolerance window or day-based classification.
    Adjacent intervals contain each event once, including at midnight.
    """
    start = _utc(start)
    _require_aware(end)
    end = end.astimezone(timezone.utc)
    if end < start:
        raise ValueError("end must not precede start")
    if end > _END:
        raise AstronomyRangeError("phase interval extends beyond 2099 UTC")
    # Guard lunations on either side of the mean-phase estimate.
    first = math.floor((julian_day(start)-2451550.09765)/29.530588853)-1
    last = math.ceil((julian_day(end)-2451550.09765)/29.530588853)+1
    events = []
    for n in range(first, last+1):
        for i, phase in enumerate(PrincipalPhase):
            event = _event(n+i/4, phase)
            if start <= event.at_utc < end and _MIN <= event.at_utc < _END:
                events.append(event)
    return tuple(sorted(events, key=lambda e: e.at_utc))


def upcoming_lunar_phases(moment: datetime, zone: tzinfo = timezone.utc) -> UpcomingLunarPhases:
    """Strictly later than the request, matching the legacy 'next' contract.

    At the exact computed event instant it is elapsed. Missing endpoint
    phases return None, never an auxiliary-year event or a made-up date.
    """
    utc = _utc(moment)
    events = lunar_phase_events(utc, min(utc+timedelta(days=40), _END))
    selected = {}
    for event in events:
        if event.at_utc > utc:
            selected.setdefault(event.phase, event)
    return UpcomingLunarPhases(utc, tuple(sorted(selected.values(), key=lambda e: e.at_utc)), zone)
