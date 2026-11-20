"""Upper meridian passages and civil-day maxima of airless lunar center altitude.

Reuses task 2.1 lunar theory and sea-level topocentric observer. Times are UTC;
local properties preserve offset/fold. End-boundary values are one-sided limits,
not events belonging to the requested half-open civil day.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone, tzinfo
from enum import Enum
import math

from .astronomy import validate_astronomy_year, _validate_coordinates
from .lunar_horizon import _topocentric, _crossings, LunarEventState

LUNAR_TRANSIT_VERSION = "awqati-meeus47-topocentric-transit-maximum-v1"


class LunarTransitState(Enum):
    AVAILABLE = "available"
    MULTIPLE = "multiple"
    NO_EVENT = "noEventInCivilDay"
    UNDEFINED_MERIDIAN = "undefinedMeridianAtGeographicPole"
    CALCULATION_ERROR = "calculationError"


class MaximumKind(Enum):
    INTERIOR = "interiorMaximum"
    DAY_START = "civilDayStart"
    DAY_END_LIMIT = "civilDayEndLimit"


@dataclass(frozen=True, slots=True)
class LunarAltitudePoint:
    at_utc: datetime
    altitude_degrees: float

    @property
    def above_horizon(self) -> bool:
        """Center above geometric horizon; never a claim of visibility."""
        return self.altitude_degrees > 0


@dataclass(frozen=True, slots=True)
class LunarMaximum(LunarAltitudePoint):
    kind: MaximumKind

    @property
    def attained(self) -> bool:
        return self.kind is not MaximumKind.DAY_END_LIMIT


@dataclass(frozen=True, slots=True)
class LunarTransitDay:
    local_date: date
    zone: tzinfo
    civil_intervals_utc: tuple[tuple[datetime, datetime], ...]
    transits: tuple[LunarAltitudePoint, ...]
    transit_state: LunarTransitState
    maxima: tuple[LunarMaximum, ...]
    maximum_state: LunarEventState
    algorithm_version: str = LUNAR_TRANSIT_VERSION

    @property
    def transits_local(self) -> tuple[datetime, ...]:
        return tuple(p.at_utc.astimezone(self.zone) for p in self.transits)

    @property
    def maxima_local(self) -> tuple[datetime, ...]:
        """An end limit converts to the following date: do not call it today's event."""
        return tuple(p.at_utc.astimezone(self.zone) for p in self.maxima)

    @property
    def center_below_horizon_all_day(self) -> bool | None:
        if not self.maxima:
            return None
        return all(p.altitude_degrees < 0 for p in self.maxima)


def _civil_intervals(day: date, zone: tzinfo):
    """Find actual UTC intervals of an IANA civil date, including gaps/folds.

    Minute membership scan is timezone-only (no lunar evaluations). Bundled
    IANA date segments are longer than a minute. Binary refinement preserves
    historical second-level transitions, repeated and skipped dates.
    """
    start = datetime.combine(day, datetime.min.time(), timezone.utc)-timedelta(days=1)
    end = start+timedelta(days=3)
    belongs = lambda t: t.astimezone(zone).date() == day
    previous, inside = start, belongs(start)
    opened = start if inside else None
    intervals = []
    at = start
    while at < end:
        at = min(at+timedelta(minutes=1), end)
        current = belongs(at)
        if current != inside:
            left, right = previous, at
            while right-left > timedelta(microseconds=1):
                mid = left+(right-left)//2
                if belongs(mid) == inside:
                    left = mid
                else:
                    right = mid
            if current:
                opened = right
            else:
                intervals.append((opened, right))
                opened = None
        previous, inside = at, current
    if opened is not None:
        intervals.append((opened, end))
    return tuple(intervals)


def lunar_transit_day(day: date, latitude: float, longitude: float, zone: tzinfo) -> LunarTransitDay:
    """All H=0 upper transits and global altitude maximum candidates, 1901–2099.

    Compare stationary maxima AND both limits of every civil interval. Return
    all equal global candidates (within 1e-12 degrees), ordered in UTC. A skipped
    date has no maximum; an arithmetic failure is explicitly different.
    At exact geographic poles a local meridian is undefined, but altitude is
    still meaningful. Input errors raise ValueError, never no-event states.
    """
    validate_astronomy_year(day.year)
    _validate_coordinates(latitude, longitude)
    if zone is None or datetime.combine(day, datetime.min.time(), zone).utcoffset() is None:
        raise ValueError("an aware civil timezone is required")
    intervals = _civil_intervals(day, zone)
    transits, candidates = [], []
    try:
        # Repeated evaluations in both searches share task 2.1 coordinates.
        cache = {}
        def coordinates(t):
            if t not in cache:
                cache[t] = _topocentric(t, latitude, longitude)
            return cache[t]
        def altitude(t):
            return coordinates(t)[0]
        def derivative(t):
            return altitude(t+timedelta(seconds=.5))-altitude(t-timedelta(seconds=.5))
        for start, end in intervals:
            if abs(latitude) != 90:
                # sin(H) also vanishes at lower transit; cos(H)>0 rejects it.
                meridian = lambda t: math.sin(coordinates(t)[2])
                for t, _ in _crossings(meridian, start-timedelta(minutes=10), end+timedelta(minutes=10)):
                    # Legacy root isolation is precise to .02s. Snap only a
                    # numerically zero boundary, so an end root cannot leak
                    # into this half-open day through the bisection midpoint.
                    for boundary in (start,end):
                        if abs((t-boundary).total_seconds())<.03 and abs(meridian(boundary))<1e-12:
                            t=boundary
                    if start <= t < end and math.cos(coordinates(t)[2]) > 0:
                        transits.append(LunarAltitudePoint(t, altitude(t)))
            candidates.extend((LunarMaximum(start, altitude(start), MaximumKind.DAY_START),
                               LunarMaximum(end, altitude(end), MaximumKind.DAY_END_LIMIT)))
            # Pad to include the final partial sampling step and maxima arbitrarily
            # near either boundary; date membership is applied after root finding.
            for t, increasing in _crossings(derivative, start-timedelta(minutes=10), end+timedelta(minutes=10)):
                for boundary in (start,end):
                    if abs((t-boundary).total_seconds())<.03 and derivative(boundary)==0:
                        t=boundary
                if not increasing and start < t < end:
                    candidates.append(LunarMaximum(t, altitude(t), MaximumKind.INTERIOR))
        greatest = max((p.altitude_degrees for p in candidates), default=None)
        maxima = tuple(sorted((p for p in candidates if greatest-p.altitude_degrees <= 1e-12), key=lambda p:p.at_utc))
    except (ArithmeticError, ValueError):
        return LunarTransitDay(day, zone, intervals, (), LunarTransitState.CALCULATION_ERROR,
                               (), LunarEventState.CALCULATION_ERROR)
    transits.sort(key=lambda p:p.at_utc)
    state = (LunarTransitState.UNDEFINED_MERIDIAN if abs(latitude) == 90 else
             LunarTransitState.MULTIPLE if len(transits)>1 else
             LunarTransitState.AVAILABLE if transits else LunarTransitState.NO_EVENT)
    maximum_state = (LunarEventState.MULTIPLE if len(maxima)>1 else
                     LunarEventState.AVAILABLE if maxima else LunarEventState.NO_EVENT)
    return LunarTransitDay(day, zone, intervals, tuple(transits), state, maxima, maximum_state)
