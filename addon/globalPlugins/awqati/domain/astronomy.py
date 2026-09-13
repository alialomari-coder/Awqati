"""Pure offline astronomical calculations for Awqati task 2.3.

Algorithms are pinned and documented in docs/data_sources.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from enum import Enum
import math


ASTRONOMY_ALGORITHM_VERSION = "awqati-astronomy-meeus2-noaa-1901-2099-v2"
ASTRONOMY_MIN_YEAR = 1901
ASTRONOMY_MAX_YEAR = 2099
_ASTRONOMY_AUXILIARY_MIN_YEAR = ASTRONOMY_MIN_YEAR - 1
_ASTRONOMY_AUXILIARY_MAX_YEAR = ASTRONOMY_MAX_YEAR + 1
_NEXT_SUNRISE_SEARCH_DAYS = 370
APPARENT_SUN_ZENITH_DEGREES = 90.833
MOON_PHASE_SECTOR_DEGREES = 45.0


class AstronomyRangeError(ValueError):
	"""Requested instant is outside the versioned accuracy range."""


class Season(Enum):
	SPRING = "spring"
	SUMMER = "summer"
	AUTUMN = "autumn"
	WINTER = "winter"


class SeasonEvent(Enum):
	MARCH_EQUINOX = "marchEquinox"
	JUNE_SOLSTICE = "juneSolstice"
	SEPTEMBER_EQUINOX = "septemberEquinox"
	DECEMBER_SOLSTICE = "decemberSolstice"


class SolarDayState(Enum):
	NORMAL = "normal"
	POLAR_DAY = "polarDay"
	POLAR_NIGHT = "polarNight"


class MoonPhase(Enum):
	NEW_MOON = "newMoon"
	WAXING_CRESCENT = "waxingCrescent"
	FIRST_QUARTER = "firstQuarter"
	WAXING_GIBBOUS = "waxingGibbous"
	FULL_MOON = "fullMoon"
	WANING_GIBBOUS = "waningGibbous"
	LAST_QUARTER = "lastQuarter"
	WANING_CRESCENT = "waningCrescent"


@dataclass(frozen=True, slots=True)
class SeasonalEvent:
	event: SeasonEvent
	at_utc: datetime


@dataclass(frozen=True, slots=True)
class SolarDay:
	state: SolarDayState
	sunrise_utc: datetime | None
	sunset_utc: datetime | None
	next_sunrise_utc: datetime | None
	daylight: timedelta
	night: timedelta


@dataclass(frozen=True, slots=True)
class LunarFacts:
	phase: MoonPhase
	elongation_degrees: float
	age_days: float
	illumination_fraction: float
	previous_new_moon_utc: datetime
	next_new_moon_utc: datetime
	next_full_moon_utc: datetime


@dataclass(frozen=True, slots=True)
class AstronomyReading:
	local_date: date
	observed_at_local: datetime
	current_season: Season
	current_season_started: SeasonalEvent
	next_seasonal_event: SeasonalEvent
	next_seasonal_event_local: datetime
	solar_day: SolarDay
	daylight_change_from_previous_day: timedelta | None
	sunrise_local: datetime | None
	sunset_local: datetime | None
	lunar: LunarFacts
	next_new_moon_local: datetime
	next_full_moon_local: datetime
	algorithm_version: str = ASTRONOMY_ALGORITHM_VERSION


_SEASON_TERMS = (
	(485, 324.96, 1934.136), (203, 337.23, 32964.467),
	(199, 342.08, 20.186), (182, 27.85, 445267.112),
	(156, 73.14, 45036.886), (136, 171.52, 22518.443),
	(77, 222.54, 65928.934), (74, 296.72, 3034.906),
	(70, 243.58, 9037.513), (58, 119.81, 33718.147),
	(52, 297.17, 150.678), (50, 21.02, 2281.226),
	(45, 247.54, 29929.562), (44, 325.15, 31555.956),
	(29, 60.93, 4443.417), (18, 155.12, 67555.328),
	(17, 288.79, 4562.452), (16, 198.04, 62894.029),
	(14, 199.76, 31436.921), (12, 95.39, 14577.848),
	(12, 287.11, 31931.756), (12, 320.81, 34777.259),
	(9, 227.73, 1222.114), (8, 15.45, 16859.074),
)
_PHASES = (
	MoonPhase.NEW_MOON, MoonPhase.WAXING_CRESCENT,
	MoonPhase.FIRST_QUARTER, MoonPhase.WAXING_GIBBOUS,
	MoonPhase.FULL_MOON, MoonPhase.WANING_GIBBOUS,
	MoonPhase.LAST_QUARTER, MoonPhase.WANING_CRESCENT,
)
_LUNAR_CORRECTION_ANGLES_E_POWERS = (
	0, 1, 0, 0, 1, 1, 2, 0, 0, 1, 0, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
)
_NEW_MOON_CORRECTION_COEFFICIENTS = (
	-0.40720, 0.17241, 0.01608, 0.01039, 0.00739, -0.00514, 0.00208,
	-0.00111, -0.00057, 0.00056, -0.00042, 0.00042, 0.00038, -0.00024,
	-0.00017, -0.00007, 0.00004, 0.00004, 0.00003, 0.00003, -0.00003,
	0.00003, -0.00002, -0.00002, 0.00002,
)
_FULL_MOON_CORRECTION_COEFFICIENTS = (
	-0.40614, 0.17302, 0.01614, 0.01043, 0.00734, -0.00515, 0.00209,
	-0.00111, -0.00057, 0.00056, -0.00042, 0.00042, 0.00038, -0.00024,
	-0.00017, -0.00007, 0.00004, 0.00004, 0.00003, 0.00003, -0.00003,
	0.00003, -0.00002, -0.00002, 0.00002,
)


def validate_astronomy_year(year: int) -> None:
	if not ASTRONOMY_MIN_YEAR <= year <= ASTRONOMY_MAX_YEAR:
		raise AstronomyRangeError(
			f"astronomy supports civil years {ASTRONOMY_MIN_YEAR} through {ASTRONOMY_MAX_YEAR}"
		)


def seasonal_event_utc(year: int, event: SeasonEvent) -> datetime:
	"""Meeus chapter 27 event instant converted from TT to UTC."""
	validate_astronomy_year(year)
	return _seasonal_event_utc(year, event)


def _seasonal_event_utc(year: int, event: SeasonEvent) -> datetime:
	_validate_auxiliary_year(year)
	y = (year - 2000.0) / 1000.0
	polynomials = {
		SeasonEvent.MARCH_EQUINOX: (2451623.80984, 365242.37404, 0.05169, -0.00411, -0.00057),
		SeasonEvent.JUNE_SOLSTICE: (2451716.56767, 365241.62603, 0.00325, 0.00888, -0.00030),
		SeasonEvent.SEPTEMBER_EQUINOX: (2451810.21715, 365242.01767, -0.11575, 0.00337, 0.00078),
		SeasonEvent.DECEMBER_SOLSTICE: (2451900.05952, 365242.74049, -0.06223, -0.00823, 0.00032),
	}
	c0, c1, c2, c3, c4 = polynomials[event]
	jde0 = c0 + c1 * y + c2 * y**2 + c3 * y**3 + c4 * y**4
	t = (jde0 - 2451545.0) / 36525.0
	w = math.radians(35999.373 * t - 2.47)
	delta_lambda = 1 + 0.0334 * math.cos(w) + 0.0007 * math.cos(2 * w)
	periodic = sum(a * math.cos(math.radians(b + c * t)) for a, b, c in _SEASON_TERMS)
	jde_tt = jde0 + 0.00001 * periodic / delta_lambda
	return _tt_jd_to_utc(jde_tt)


def season_at(moment_utc: datetime, latitude: float) -> tuple[Season, SeasonalEvent]:
	_require_aware(moment_utc)
	validate_astronomy_year(moment_utc.year)
	events: list[SeasonalEvent] = []
	for year in (moment_utc.year - 1, moment_utc.year):
		for event in SeasonEvent:
			events.append(SeasonalEvent(event, _seasonal_event_utc(year, event)))
	past_events = [item for item in events if item.at_utc <= moment_utc]
	if not past_events:
		raise AstronomyRangeError("cannot locate the season boundary for the requested instant")
	latest = max(past_events, key=lambda item: item.at_utc)
	north = {
		SeasonEvent.MARCH_EQUINOX: Season.SPRING,
		SeasonEvent.JUNE_SOLSTICE: Season.SUMMER,
		SeasonEvent.SEPTEMBER_EQUINOX: Season.AUTUMN,
		SeasonEvent.DECEMBER_SOLSTICE: Season.WINTER,
	}
	south = {
		SeasonEvent.MARCH_EQUINOX: Season.AUTUMN,
		SeasonEvent.JUNE_SOLSTICE: Season.WINTER,
		SeasonEvent.SEPTEMBER_EQUINOX: Season.SPRING,
		SeasonEvent.DECEMBER_SOLSTICE: Season.SUMMER,
	}
	return (north if latitude >= 0 else south)[latest.event], latest


def next_seasonal_event(moment_utc: datetime) -> SeasonalEvent:
	_require_aware(moment_utc)
	validate_astronomy_year(moment_utc.year)
	candidates: list[SeasonalEvent] = []
	for year in (moment_utc.year, moment_utc.year + 1):
		for event in SeasonEvent:
			value = SeasonalEvent(event, _seasonal_event_utc(year, event))
			if value.at_utc > moment_utc:
				candidates.append(value)
	if not candidates:
		raise AstronomyRangeError("no later seasonal event exists in the supported range")
	return min(candidates, key=lambda item: item.at_utc)


def solar_day(
	day: date,
	latitude: float,
	longitude: float,
	*,
	utc_anchor_day: date | None = None,
) -> SolarDay:
	"""NOAA apparent-sun day and the absolute interval to the next sunrise."""
	validate_astronomy_year(day.year)
	_validate_coordinates(latitude, longitude)
	anchor_day = utc_anchor_day or day
	_validate_auxiliary_year(anchor_day.year)
	if abs(anchor_day.toordinal() - day.toordinal()) > 1:
		raise ValueError("utc_anchor_day must be within one day of the requested civil day")
	state, sunrise, sunset = _solar_events(anchor_day, latitude, longitude)
	if state is SolarDayState.POLAR_NIGHT:
		return SolarDay(state, None, None, None, timedelta(0), timedelta(days=1))
	if state is SolarDayState.POLAR_DAY:
		return SolarDay(state, None, None, None, timedelta(days=1), timedelta(0))
	assert sunrise is not None and sunset is not None
	next_sunrise = _next_sunrise_after(sunset, latitude, longitude, anchor_day)
	return SolarDay(
		state=state,
		sunrise_utc=sunrise,
		sunset_utc=sunset,
		next_sunrise_utc=next_sunrise,
		daylight=sunset - sunrise,
		night=next_sunrise - sunset,
	)


def _solar_events(
	day: date,
	latitude: float,
	longitude: float,
) -> tuple[SolarDayState, datetime | None, datetime | None]:
	_validate_auxiliary_year(day.year)
	base, noon_minutes, t = _solar_noon(day, longitude)
	declination = _sun_declination(t)
	equation = _equation_of_time(t)
	latitude_r = math.radians(latitude)
	declination_r = math.radians(declination)
	denominator = math.cos(latitude_r) * math.cos(declination_r)
	if abs(denominator) < 1e-15:
		cos_hour = math.inf if math.sin(latitude_r) * math.sin(declination_r) < 0 else -math.inf
	else:
		cos_hour = (
			math.cos(math.radians(APPARENT_SUN_ZENITH_DEGREES))
			/ denominator - math.tan(latitude_r) * math.tan(declination_r)
		)
	if cos_hour > 1:
		return SolarDayState.POLAR_NIGHT, None, None
	if cos_hour < -1:
		return SolarDayState.POLAR_DAY, None, None
	hour_angle = math.degrees(math.acos(cos_hour))
	noon_minutes = 720.0 - 4.0 * longitude - equation
	sunrise = base + timedelta(minutes=noon_minutes - 4.0 * hour_angle)
	sunset = base + timedelta(minutes=noon_minutes + 4.0 * hour_angle)
	return SolarDayState.NORMAL, sunrise, sunset


def _next_sunrise_after(
	sunset: datetime,
	latitude: float,
	longitude: float,
	anchor_day: date,
) -> datetime:
	"""Return the first later NOAA sunrise without fixed-interval sampling."""
	for offset in range(1, _NEXT_SUNRISE_SEARCH_DAYS + 1):
		candidate_day = anchor_day + timedelta(days=offset)
		_validate_auxiliary_year(candidate_day.year)
		state, sunrise, _sunset = _solar_events(candidate_day, latitude, longitude)
		if state is SolarDayState.NORMAL and sunrise is not None and sunrise > sunset:
			return sunrise
		if state is SolarDayState.POLAR_DAY:
			# A normal sunset immediately before a polar-day cycle still has a
			# real upward crossing.  Bracket it by the cycle's lower and upper
			# culminations, so even an arbitrarily short night cannot be skipped.
			base, noon_minutes, _noon_t = _solar_noon(candidate_day, longitude)
			noon = base + timedelta(minutes=noon_minutes)
			if noon <= sunset:
				continue
			minimum = _bounded_horizon_minimum(sunset, noon, latitude, longitude)
			if (
				_solar_horizon_value(minimum, latitude, longitude) < 0
				and _solar_horizon_value(noon, latitude, longitude) >= 0
			):
				return _bisect_upward_crossing(minimum, noon, latitude, longitude)
	raise AstronomyRangeError("cannot locate the next astronomical sunrise")


def _solar_noon(day: date, longitude: float) -> tuple[datetime, float, float]:
	"""Return UTC midnight and the NOAA two-pass solar-noon minute."""
	base = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
	jd = julian_day(base)
	initial_t = _julian_century(jd)
	noon_minutes = 720.0 - 4.0 * longitude - _equation_of_time(initial_t)
	noon_t = _julian_century(jd + noon_minutes / 1440.0)
	return base, 720.0 - 4.0 * longitude - _equation_of_time(noon_t), noon_t


def _bounded_horizon_minimum(
	start: datetime,
	end: datetime,
	latitude: float,
	longitude: float,
) -> datetime:
	"""Locate the lower culmination in one sunset-to-noon interval."""
	left, right = start, end
	ratio = (math.sqrt(5.0) - 1.0) / 2.0
	first = right - (right - left) * ratio
	second = left + (right - left) * ratio
	first_value = _solar_horizon_value(first, latitude, longitude)
	second_value = _solar_horizon_value(second, latitude, longitude)
	for _ in range(80):
		if first_value <= second_value:
			right, second, second_value = second, first, first_value
			first = right - (right - left) * ratio
			first_value = _solar_horizon_value(first, latitude, longitude)
		else:
			left, first, first_value = first, second, second_value
			second = left + (right - left) * ratio
			second_value = _solar_horizon_value(second, latitude, longitude)
	return left + (right - left) / 2


def _bisect_upward_crossing(
	below: datetime,
	above: datetime,
	latitude: float,
	longitude: float,
) -> datetime:
	"""Refine one upward apparent-horizon crossing from an extrema bracket."""
	low, high = below, above
	for _ in range(60):
		middle = low + (high - low) / 2
		if _solar_horizon_value(middle, latitude, longitude) >= 0:
			high = middle
		else:
			low = middle
	return high


def _solar_horizon_value(moment: datetime, latitude: float, longitude: float) -> float:
	utc = moment.astimezone(timezone.utc)
	t = _julian_century(julian_day(utc))
	equation = _equation_of_time(t)
	declination = math.radians(_sun_declination(t))
	minutes = (
		utc.hour * 60.0 + utc.minute + utc.second / 60.0 + utc.microsecond / 60000000.0
	)
	true_solar_minutes = (minutes + equation + 4.0 * longitude) % 1440.0
	hour_angle = math.radians(true_solar_minutes / 4.0 - 180.0)
	latitude_r = math.radians(latitude)
	cos_zenith = (
		math.sin(latitude_r) * math.sin(declination)
		+ math.cos(latitude_r) * math.cos(declination) * math.cos(hour_angle)
	)
	return cos_zenith - math.cos(math.radians(APPARENT_SUN_ZENITH_DEGREES))


def lunar_facts(moment_utc: datetime) -> LunarFacts:
	_require_aware(moment_utc)
	validate_astronomy_year(moment_utc.year)
	jd = julian_day(moment_utc.astimezone(timezone.utc))
	elongation, solar_anomaly, lunar_anomaly = _lunar_elongation(jd)
	phase = classify_moon_phase(elongation)
	phase_angle = 180.0 - elongation - 0.1468 * (
		(1 - 0.0549 * _sin(lunar_anomaly)) / (1 - 0.0167 * _sin(solar_anomaly))
	) * _sin(elongation)
	illumination = min(1.0, max(0.0, (1 + _cos(phase_angle)) / 2.0))
	previous_new = _adjacent_lunar_phase(moment_utc, full=False, forward=False)
	next_new = _adjacent_lunar_phase(moment_utc, full=False, forward=True)
	next_full = _adjacent_lunar_phase(moment_utc, full=True, forward=True)
	age = (moment_utc.astimezone(timezone.utc) - previous_new).total_seconds() / 86400.0
	return LunarFacts(phase, elongation, age, illumination, previous_new, next_new, next_full)


def classify_moon_phase(elongation_degrees: float) -> MoonPhase:
	"""Classify the continuous elongation into documented equal 45-degree sectors."""
	if not math.isfinite(elongation_degrees):
		raise ValueError("elongation_degrees must be finite")
	elongation = elongation_degrees % 360.0
	index = int(math.floor((elongation + MOON_PHASE_SECTOR_DEGREES / 2) / MOON_PHASE_SECTOR_DEGREES)) % 8
	return _PHASES[index]


def lunar_phase_event_utc(k: float) -> datetime:
	"""Meeus chapter 49 new/full phase for integer/half-integer lunation k."""
	result = _lunar_phase_event_utc(k)
	validate_astronomy_year(result.year)
	return result


def _lunar_phase_event_utc(k: float) -> datetime:
	t = k / 1236.85
	e = 1 - 0.002516 * t - 0.0000074 * t**2
	jde = (
		2451550.09765 + 29.530588853 * k + 0.0001337 * t**2
		- 0.000000150 * t**3 + 0.00000000073 * t**4
	)
	m = _fix_angle(2.5534 + 29.10535670 * k - 0.0000014 * t**2 - 0.00000011 * t**3)
	mp = _fix_angle(
		201.5643 + 385.81693528 * k + 0.0107582 * t**2
		+ 0.00001238 * t**3 - 0.000000058 * t**4
	)
	f = _fix_angle(
		160.7108 + 390.67050284 * k - 0.0016118 * t**2
		- 0.00000227 * t**3 + 0.000000011 * t**4
	)
	omega = _fix_angle(124.7746 - 1.56375580 * k + 0.0020672 * t**2 + 0.00000215 * t**3)
	is_full = abs((k - math.floor(k)) - 0.5) < 1e-10
	if not (is_full or abs(k - round(k)) < 1e-10):
		raise ValueError("only integer new-moon or half-integer full-moon k is supported")
	correction_angles = (
		mp, m, 2 * mp, 2 * f, mp - m, mp + m, 2 * m,
		mp - 2 * f, mp + 2 * f, 2 * mp + m, 3 * mp, m + 2 * f,
		m - 2 * f, 2 * mp - m, omega, mp + 2 * m, 2 * mp - 2 * f,
		3 * m, mp + m - 2 * f, 2 * mp + 2 * f, mp + m + 2 * f,
		mp - m + 2 * f, mp - m - 2 * f, 3 * mp + m, 4 * mp,
	)
	coefficients = (
		_FULL_MOON_CORRECTION_COEFFICIENTS
		if is_full else _NEW_MOON_CORRECTION_COEFFICIENTS
	)
	correction = sum(
		coefficient * e**e_power * _sin(angle)
		for coefficient, e_power, angle in zip(
			coefficients, _LUNAR_CORRECTION_ANGLES_E_POWERS, correction_angles,
		)
	)
	angles = (
		299.77 + 0.107408 * k - 0.009173 * t**2, 251.88 + 0.016321 * k,
		251.83 + 26.651886 * k, 349.42 + 36.412478 * k,
		84.66 + 18.206239 * k, 141.74 + 53.303771 * k,
		207.14 + 2.453732 * k, 154.84 + 7.306860 * k,
		34.52 + 27.261239 * k, 207.19 + 0.121824 * k,
		291.34 + 1.844379 * k, 161.72 + 24.198154 * k,
		239.56 + 25.513099 * k, 331.55 + 3.592518 * k,
	)
	weights = (0.000325, 0.000165, 0.000164, 0.000126, 0.000110, 0.000062,
		0.000060, 0.000056, 0.000047, 0.000042, 0.000040, 0.000037, 0.000035, 0.000023)
	jde += correction + sum(weight * _sin(angle) for weight, angle in zip(weights, angles))
	return _tt_jd_to_utc(jde)


def julian_day(value: datetime) -> float:
	_require_aware(value)
	utc = value.astimezone(timezone.utc)
	unix_epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
	return 2440587.5 + (utc - unix_epoch).total_seconds() / 86400.0


def delta_t_seconds(year: int, month: int = 7) -> float:
	"""NASA Espenak-Meeus piecewise Delta T polynomials."""
	validate_astronomy_year(year)
	return _delta_t_seconds(year, month)


def _delta_t_seconds(year: int, month: int = 7) -> float:
	_validate_auxiliary_year(year)
	y = year + (month - 0.5) / 12.0
	if y < 1920:
		t = y - 1900
		return -2.79 + 1.494119 * t - 0.0598939 * t**2 + 0.0061966 * t**3 - 0.000197 * t**4
	if y < 1941:
		t = y - 1920
		return 21.20 + 0.84493 * t - 0.076100 * t**2 + 0.0020936 * t**3
	if y < 1961:
		t = y - 1950
		return 29.07 + 0.407 * t - t**2 / 233 + t**3 / 2547
	if y < 1986:
		t = y - 1975
		return 45.45 + 1.067 * t - t**2 / 260 - t**3 / 718
	if y < 2005:
		t = y - 2000
		return (
			63.86 + 0.3345 * t - 0.060374 * t**2 + 0.0017275 * t**3
			+ 0.000651814 * t**4 + 0.00002373599 * t**5
		)
	if y < 2050:
		t = y - 2000
		return 62.92 + 0.32217 * t + 0.005589 * t**2
	u = (y - 1820) / 100
	return -20 + 32 * u**2 - 0.5628 * (2150 - y)


def _adjacent_lunar_phase(moment: datetime, *, full: bool, forward: bool) -> datetime:
	utc = moment.astimezone(timezone.utc)
	decimal_year = utc.year + (utc.timetuple().tm_yday - 1 + utc.hour / 24) / 365.2425
	base = (decimal_year - 2000.0) * 12.3685
	base_k = math.floor(base)
	candidates = sorted(
		_lunar_phase_event_utc(integer_k + (0.5 if full else 0.0))
		for integer_k in range(base_k - 3, base_k + 5)
	)
	eligible = (
		[candidate for candidate in candidates if candidate > utc]
		if forward else [candidate for candidate in candidates if candidate <= utc]
	)
	if eligible:
		return min(eligible) if forward else max(eligible)
	raise AstronomyRangeError("cannot locate adjacent lunar phase in the supported range")


def _lunar_elongation(jd: float) -> tuple[float, float, float]:
	t = (jd - 2451545.0) / 36525.0
	l0 = _fix_angle(218.3164477 + 481267.88123421 * t - 0.0015786 * t**2 + t**3 / 538841)
	d = _fix_angle(297.8501921 + 445267.1114034 * t - 0.0018819 * t**2 + t**3 / 545868)
	m = _fix_angle(357.5291092 + 35999.0502909 * t - 0.0001536 * t**2)
	mp = _fix_angle(134.9633964 + 477198.8675055 * t + 0.0087414 * t**2 + t**3 / 69699)
	f = _fix_angle(93.2720950 + 483202.0175233 * t - 0.0036539 * t**2)
	moon = l0 + (
		6.289 * _sin(mp) + 1.274 * _sin(2 * d - mp) + 0.658 * _sin(2 * d)
		+ 0.214 * _sin(2 * mp) - 0.186 * _sin(m) - 0.114 * _sin(2 * f)
		+ 0.059 * _sin(2 * d - 2 * mp) + 0.057 * _sin(2 * d - m - mp)
		+ 0.053 * _sin(2 * d + mp) + 0.046 * _sin(2 * d - m)
		+ 0.041 * _sin(m - mp) - 0.035 * _sin(d) - 0.031 * _sin(m + mp)
		- 0.015 * _sin(2 * f - 2 * d) + 0.011 * _sin(mp - 4 * d)
	)
	sun = _sun_apparent_longitude(t)
	return _fix_angle(moon - sun), m, mp


def _sun_apparent_longitude(t: float) -> float:
	l0 = _fix_angle(280.46646 + t * (36000.76983 + 0.0003032 * t))
	m = _fix_angle(357.52911 + t * (35999.05029 - 0.0001537 * t))
	c = (
		(1.914602 - t * (0.004817 + 0.000014 * t)) * _sin(m)
		+ (0.019993 - 0.000101 * t) * _sin(2 * m) + 0.000289 * _sin(3 * m)
	)
	omega = 125.04 - 1934.136 * t
	return _fix_angle(l0 + c - 0.00569 - 0.00478 * _sin(omega))


def _equation_of_time(t: float) -> float:
	epsilon = math.radians(_obliquity_correction(t))
	l0 = math.radians(_fix_angle(280.46646 + t * (36000.76983 + 0.0003032 * t)))
	eccentricity = 0.016708634 - t * (0.000042037 + 0.0000001267 * t)
	m = math.radians(_fix_angle(357.52911 + t * (35999.05029 - 0.0001537 * t)))
	y = math.tan(epsilon / 2) ** 2
	value = (
		y * math.sin(2 * l0) - 2 * eccentricity * math.sin(m)
		+ 4 * eccentricity * y * math.sin(m) * math.cos(2 * l0)
		- 0.5 * y**2 * math.sin(4 * l0) - 1.25 * eccentricity**2 * math.sin(2 * m)
	)
	return math.degrees(value) * 4


def _sun_declination(t: float) -> float:
	epsilon = math.radians(_obliquity_correction(t))
	lambda_sun = math.radians(_sun_apparent_longitude(t))
	return math.degrees(math.asin(math.sin(epsilon) * math.sin(lambda_sun)))


def _obliquity_correction(t: float) -> float:
	seconds = 21.448 - t * (46.815 + t * (0.00059 - t * 0.001813))
	mean = 23 + (26 + seconds / 60) / 60
	return mean + 0.00256 * _cos(125.04 - 1934.136 * t)


def _julian_century(jd: float) -> float:
	return (jd - 2451545.0) / 36525.0


def _tt_jd_to_utc(jde_tt: float) -> datetime:
	unix_epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
	approx = unix_epoch + timedelta(days=jde_tt - 2440587.5)
	_validate_auxiliary_year(approx.year)
	delta = _delta_t_seconds(approx.year, approx.month)
	result = approx - timedelta(seconds=delta)
	_validate_auxiliary_year(result.year)
	return result


def _validate_auxiliary_year(year: int) -> None:
	if not _ASTRONOMY_AUXILIARY_MIN_YEAR <= year <= _ASTRONOMY_AUXILIARY_MAX_YEAR:
		raise AstronomyRangeError(
			"astronomy auxiliary calculations support only the adjacent civil years "
			f"{_ASTRONOMY_AUXILIARY_MIN_YEAR} through {_ASTRONOMY_AUXILIARY_MAX_YEAR}"
		)


def _validate_coordinates(latitude: float, longitude: float) -> None:
	if not math.isfinite(latitude) or not -90 <= latitude <= 90:
		raise ValueError("latitude must be finite and between -90 and 90")
	if not math.isfinite(longitude) or not -180 <= longitude <= 180:
		raise ValueError("longitude must be finite and between -180 and 180")


def _require_aware(value: datetime) -> None:
	if value.tzinfo is None or value.utcoffset() is None:
		raise ValueError("astronomy instants must be timezone-aware")


def _fix_angle(value: float) -> float:
	return value % 360.0


def _sin(value: float) -> float:
	return math.sin(math.radians(value))


def _cos(value: float) -> float:
	return math.cos(math.radians(value))
