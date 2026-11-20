"""Offline lunar upper-limb crossings; Meeus chapters 12, 22, 40 and 47.

Uses the shared astronomy time/range conventions. No presentation strings,
terrain model or public lunar-distance calculation.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone, tzinfo
from enum import Enum
import math

from .astronomy import (
    julian_day, validate_astronomy_year, _delta_t_seconds,
    _validate_coordinates, _sin, _cos, _obliquity_correction,
)
from ._lunar_terms import _LR, _B

LUNAR_HORIZON_VERSION = "awqati-meeus47-topocentric-upper-limb-v1"


class LunarEventState(Enum):
    AVAILABLE = "available"
    MULTIPLE = "multiple"
    NO_EVENT = "noEventInCivilDay"
    CALCULATION_ERROR = "calculationError"


@dataclass(frozen=True, slots=True)
class LunarHorizonEvents:
    """All instants, ordered in UTC, with independent status for each kind.

    Local values preserve UTC offset and fold; consumers must not deduplicate
    equal wall times. Absence never implies an event on an adjacent date.
    """
    local_date: date
    zone: tzinfo
    rises_utc: tuple[datetime, ...]
    sets_utc: tuple[datetime, ...]
    rise_state: LunarEventState
    set_state: LunarEventState
    algorithm_version: str = LUNAR_HORIZON_VERSION

    @property
    def rises_local(self) -> tuple[datetime, ...]:
        return tuple(t.astimezone(self.zone) for t in self.rises_utc)

    @property
    def sets_local(self) -> tuple[datetime, ...]:
        return tuple(t.astimezone(self.zone) for t in self.sets_utc)


def _position(moment: datetime) -> tuple[float, float, float]:
    """Apparent equatorial unit direction and internal geocentric radius.

    TT for lunar theory, UTC approximates UT1 for Earth rotation (<=0.9s).
    Four dominant nutation terms, consistent apparent sidereal correction.
    """
    jd = julian_day(moment)
    t = (jd + _delta_t_seconds(moment.year, moment.month) / 86400 - 2451545) / 36525
    l = 218.3164477 + 481267.88123421*t - .0015786*t*t + t**3/538841 - t**4/65194000
    d = 297.8501921 + 445267.1114034*t - .0018819*t*t + t**3/545868 - t**4/113065000
    m = 357.5291092 + 35999.0502909*t - .0001536*t*t + t**3/24490000
    p = 134.9633964 + 477198.8675055*t + .0087414*t*t + t**3/69699 - t**4/14712000
    f = 93.2720950 + 483202.0175233*t - .0036539*t*t - t**3/3526000 + t**4/863310000
    e = 1 - .002516*t - .0000074*t*t
    sl = sr = sb = 0.0
    for a, b, c, q, lc, rc in _LR:
        angle = a*d + b*m + c*p + q*f
        weight = e**abs(b)
        sl += lc * weight * _sin(angle)
        sr += rc * weight * _cos(angle)
    for a, b, c, q, bc in _B:
        sb += bc * e**abs(b) * _sin(a*d + b*m + c*p + q*f)
    a1, a2, a3 = 119.75 + 131.849*t, 53.09 + 479264.290*t, 313.45 + 481266.484*t
    sl += 3958*_sin(a1) + 1962*_sin(l-f) + 318*_sin(a2)
    sb += -2235*_sin(l) + 382*_sin(a3) + 175*_sin(a1-f) + 175*_sin(a1+f) + 127*_sin(l-p) - 115*_sin(l+p)
    nutation = _nutation(t)
    lon, lat = math.radians(l + sl/1e6 + nutation), math.radians(sb/1e6)
    eps = math.radians(_obliquity_correction(t))
    x = math.cos(lat)*math.cos(lon)
    y = math.cos(lat)*math.sin(lon)*math.cos(eps) - math.sin(lat)*math.sin(eps)
    z = math.cos(lat)*math.sin(lon)*math.sin(eps) + math.sin(lat)*math.cos(eps)
    return math.atan2(y, x), math.asin(z), 385000.56 + sr/1000


def _nutation(t: float) -> float:
    omega = 125.04452 - 1934.136261*t
    return (-17.20*_sin(omega) - 1.32*_sin(2*(280.4665+36000.7698*t))
            - .23*_sin(2*(218.3165+481267.8813*t)) + .21*_sin(2*omega))/3600


def _topocentric(moment: datetime, latitude: float, longitude: float) -> tuple[float, float, float]:
    """Shared geometric center altitude (degrees), range and hour angle (radians).

    Sea-level oblate-Earth observer, with parallax in both coordinates.
    No atmospheric refraction or lunar semidiameter in the returned altitude.
    """
    ra, dec, radius = _position(moment)
    jd = julian_day(moment)
    t = (jd-2451545)/36525
    theta = math.radians((280.46061837 + 360.98564736629*(jd-2451545)
             + .000387933*t*t - t**3/38710000
             + _nutation(t)*_cos(_obliquity_correction(t)) + longitude) % 360)
    phi = math.radians(latitude)
    u = math.atan2(.99664719*math.sin(phi), math.cos(phi))
    rho_cos, rho_sin = math.cos(u), .99664719*math.sin(u)
    x = radius*math.cos(dec)*math.cos(ra) - 6378.14*rho_cos*math.cos(theta)
    y = radius*math.cos(dec)*math.sin(ra) - 6378.14*rho_cos*math.sin(theta)
    z = radius*math.sin(dec) - 6378.14*rho_sin
    distance = math.sqrt(x*x+y*y+z*z)
    altitude = math.degrees(math.asin((math.cos(phi)*(x*math.cos(theta)+y*math.sin(theta)) + z*math.sin(phi))/distance))
    hour_angle = (theta - math.atan2(y, x) + math.pi) % (2*math.pi) - math.pi
    if not all(math.isfinite(v) for v in (altitude, distance, hour_angle)):
        raise ArithmeticError("non-finite topocentric lunar coordinates")
    return altitude, distance, hour_angle


def _horizon_residual(moment: datetime, latitude: float, longitude: float) -> float:
    """Task 2.1 upper limb: geometric center + semidiameter + fixed 34' refraction."""
    altitude, distance, _ = _topocentric(moment, latitude, longitude)
    result = altitude + math.degrees(math.asin(1737.4/distance)) + 34/60
    if not math.isfinite(result):
        raise ArithmeticError("non-finite lunar horizon residual")
    return result


def _crossings(function, start: datetime, end: datetime):
    """Isolate crossings, including close pairs hidden within a sample step.

    Refine turning points only to partition the horizon root search. No
    culmination or maximum-altitude result is calculated or exposed.
    A pure tangent without a sign change is neither rise nor set.
    """
    step = timedelta(minutes=10)
    samples = []
    moment = start
    while moment <= end:
        samples.append((moment, function(moment)))
        moment += step
    points = list(samples)
    for (a, fa), (b, fb), (c, fc) in zip(samples, samples[1:], samples[2:]):
        if (fb-fa)*(fc-fb) < 0:
            sign = 1 if fb < fa else -1
            left, right = a, c
            # Ternary refinement on this short, smooth turning interval.
            for _ in range(38):
                third = (right-left)/3
                p, q = left+third, right-third
                if sign*function(p) < sign*function(q):
                    right = q
                else:
                    left = p
            at = left+(right-left)/2
            points.append((at, function(at)))
    points.sort()
    roots = []
    for (a, fa), (b, fb) in zip(points, points[1:]):
        if fa*fb > 0 or fa == fb:
            continue
        rising = fb > fa
        if fa == 0:
            root = a
        elif fb == 0:
            root = b
        else:
            while (b-a).total_seconds() > .02:
                middle = a+(b-a)/2
                fm = function(middle)
                if (fm >= 0) == (fa >= 0):
                    a, fa = middle, fm
                else:
                    b = middle
            root = a+(b-a)/2
        # Verify a crossing, excluding exact tangencies and duplicate brackets.
        before, after = function(root-timedelta(seconds=.1)), function(root+timedelta(seconds=.1))
        if before*after < 0 and (not roots or (root-roots[-1][0]).total_seconds() > .1):
            roots.append((root, rising))
    return roots


def lunar_horizon_events(day: date, latitude: float, longitude: float, zone: tzinfo) -> LunarHorizonEvents:
    """All upper-limb rise/set crossings on the actual local civil date.

    Search in absolute UTC, then filter by round-trip local date. This handles
    gaps, folds, skipped dates and repeated dates without assuming 24 hours.
    Invalid input raises ValueError; numerical failure has independent explicit
    error states, never fabricated no-event data. Range: local years 1901â€“2099.
    """
    validate_astronomy_year(day.year)
    _validate_coordinates(latitude, longitude)
    if zone is None or datetime(day.year, day.month, day.day, tzinfo=zone).utcoffset() is None:
        raise ValueError("an aware civil timezone is required")
    start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc) - timedelta(days=1)
    try:
        roots = _crossings(lambda t: _horizon_residual(t, latitude, longitude), start, start+timedelta(days=3))
    except ArithmeticError:
        return LunarHorizonEvents(day, zone, (), (), LunarEventState.CALCULATION_ERROR, LunarEventState.CALCULATION_ERROR)
    rises = tuple(t for t, up in roots if up and t.astimezone(zone).date() == day)
    sets = tuple(t for t, up in roots if not up and t.astimezone(zone).date() == day)
    def state(values):
        return LunarEventState.MULTIPLE if len(values) > 1 else LunarEventState.AVAILABLE if values else LunarEventState.NO_EVENT
    return LunarHorizonEvents(day, zone, rises, sets, state(rises), state(sets))
