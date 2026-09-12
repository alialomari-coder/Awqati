"""Pure prayer-time concepts and astronomical calculation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, tzinfo
from enum import Enum
import math
from types import MappingProxyType
from typing import Mapping


SUNRISE_SUNSET_ANGLE = 0.833
NEAREST_LATITUDE = 48.5
MIN_USER_CORRECTION_MINUTES = -30
MAX_USER_CORRECTION_MINUTES = 30


class CalculationMethod(Enum):
	AUTO = "AUTO"
	MWL = "MWL"
	ISNA = "ISNA"
	EGYPT = "EGYPT"
	MAKKAH = "MAKKAH"
	KARACHI = "KARACHI"
	GULF = "GULF"
	KUWAIT = "KUWAIT"
	QATAR = "QATAR"
	SINGAPORE = "SINGAPORE"
	JAKIM = "JAKIM"
	KEMENAG = "KEMENAG"
	FRANCE = "FRANCE"
	RUSSIA = "RUSSIA"
	TUNISIA = "TUNISIA"
	ALGERIA = "ALGERIA"
	MOROCCO = "MOROCCO"
	PORTUGAL = "PORTUGAL"
	JORDAN = "JORDAN"
	TURKEY = "TURKEY"


class AsrMethod(Enum):
	STANDARD = "STANDARD"
	HANAFI = "HANAFI"


class HighLatitudeRule(Enum):
	AUTO = "AUTO"
	ANGLE_BASED = "ANGLE_BASED"
	ONE_SEVENTH = "ONE_SEVENTH"
	NIGHT_MIDDLE = "NIGHT_MIDDLE"
	NEAREST_LATITUDE = "NEAREST_LATITUDE"


class PrayerName(Enum):
	FAJR = "fajr"
	SUNRISE = "sunrise"
	DHUHR = "dhuhr"
	ASR = "asr"
	MAGHRIB = "maghrib"
	ISHA = "isha"


@dataclass(frozen=True, slots=True)
class CalculationMethodDefinition:
	code: CalculationMethod
	name: str
	fajr_angle: float
	isha_angle: float | None = None
	isha_interval_minutes: int | None = None
	isha_ramadan_interval_minutes: int | None = None
	maghrib_offset_minutes: int = 0
	experimental: bool = False

	def __post_init__(self) -> None:
		if self.code is CalculationMethod.AUTO:
			raise ValueError("AUTO is a request, not a calculation definition")
		if not self.name.strip():
			raise ValueError("method name must not be empty")
		if isinstance(self.fajr_angle, bool) or not isinstance(self.fajr_angle, (int, float)):
			raise TypeError("fajr_angle must be numeric")
		if not 0 < self.fajr_angle < 30:
			raise ValueError("fajr_angle must be between 0 and 30 degrees")
		if (self.isha_angle is None) == (self.isha_interval_minutes is None):
			raise ValueError("exactly one Isha angle or interval is required")
		if self.isha_angle is not None and not 0 < self.isha_angle < 30:
			raise ValueError("isha_angle must be between 0 and 30 degrees")
		for value in (self.isha_interval_minutes, self.isha_ramadan_interval_minutes):
			if value is not None and (isinstance(value, bool) or not isinstance(value, int)):
				raise TypeError("Isha intervals must be whole minutes")
			if value is not None and value <= 0:
				raise ValueError("Isha intervals must be positive")
		if isinstance(self.maghrib_offset_minutes, bool) or not isinstance(self.maghrib_offset_minutes, int):
			raise TypeError("maghrib_offset_minutes must be whole minutes")
		if not isinstance(self.experimental, bool):
			raise TypeError("experimental must be boolean")
		if self.isha_ramadan_interval_minutes is not None and self.isha_interval_minutes is None:
			raise ValueError("a Ramadan interval requires a regular Isha interval")


@dataclass(frozen=True, slots=True)
class PrayerCorrections:
	fajr: int = 0
	sunrise: int = 0
	dhuhr: int = 0
	asr: int = 0
	maghrib: int = 0
	isha: int = 0

	def __post_init__(self) -> None:
		for prayer in PrayerName:
			value = getattr(self, prayer.value)
			if isinstance(value, bool) or not isinstance(value, int):
				raise TypeError("prayer corrections must be whole minutes")
			if not MIN_USER_CORRECTION_MINUTES <= value <= MAX_USER_CORRECTION_MINUTES:
				raise ValueError("prayer corrections must be between -30 and 30 minutes")

	def as_mapping(self) -> Mapping[str, int]:
		return MappingProxyType({prayer.value: getattr(self, prayer.value) for prayer in PrayerName})


@dataclass(frozen=True, slots=True)
class PrayerCalculationRequest:
	local_date: date
	latitude: float
	longitude: float
	timezone_id: str
	calculation_method: CalculationMethod
	asr_method: AsrMethod
	high_latitude_rule: HighLatitudeRule
	country_code: str | None = None
	corrections: PrayerCorrections = field(default_factory=PrayerCorrections)
	is_ramadan: bool | None = None

	def __post_init__(self) -> None:
		if not isinstance(self.local_date, date) or isinstance(self.local_date, datetime):
			raise TypeError("local_date must be a Gregorian date")
		if not math.isfinite(self.latitude) or not -90 <= self.latitude <= 90:
			raise ValueError("latitude must be finite and between -90 and 90")
		if not math.isfinite(self.longitude) or not -180 <= self.longitude <= 180:
			raise ValueError("longitude must be finite and between -180 and 180")
		if not self.timezone_id.strip():
			raise ValueError("timezone_id must not be empty")
		if self.calculation_method is CalculationMethod.AUTO and not (self.country_code or "").strip():
			raise ValueError("AUTO calculation requires an explicit country code")
		if self.country_code is not None:
			code = self.country_code.strip().upper()
			if len(code) != 2 or not code.isascii() or not code.isalpha():
				raise ValueError("country_code must be a two-letter ISO code")
			object.__setattr__(self, "country_code", code)
		if self.is_ramadan is not None and not isinstance(self.is_ramadan, bool):
			raise TypeError("is_ramadan must be true, false, or omitted")


@dataclass(frozen=True, slots=True)
class PrayerCalculationMetadata:
	requested_method: CalculationMethod
	effective_method: CalculationMethod
	asr_method: AsrMethod
	timezone_id: str
	requested_high_latitude_rule: HighLatitudeRule
	effective_high_latitude_rule: HighLatitudeRule | None
	angle_based_used: bool
	high_latitude_fallback_used: bool
	fallback_latitude: float | None
	method_offsets_minutes: Mapping[str, int]
	user_corrections_minutes: Mapping[str, int]
	isha_interval_minutes: int | None
	is_ramadan: bool | None
	rounding: str = "nearest minute, half up"


@dataclass(frozen=True, slots=True)
class PrayerTimes:
	fajr: datetime
	sunrise: datetime
	dhuhr: datetime
	asr: datetime
	maghrib: datetime
	isha: datetime
	metadata: PrayerCalculationMetadata

	def __post_init__(self) -> None:
		for prayer in PrayerName:
			value = getattr(self, prayer.value)
			if value.tzinfo is None or value.utcoffset() is None:
				raise ValueError("prayer times must be timezone-aware")


class RamadanContextRequired(ValueError):
	"""Raised when a seasonal method cannot choose an interval honestly."""


class PrayerCalculationError(ValueError):
	"""Raised when the requested astronomical event cannot be calculated."""


class CountryMethodResolver:
	"""Resolve an explicit ISO country code from an already-loaded versioned map."""

	def __init__(self, mapping: Mapping[str, CalculationMethod], fallback: CalculationMethod) -> None:
		if fallback is CalculationMethod.AUTO:
			raise ValueError("country fallback cannot be AUTO")
		normalized: dict[str, CalculationMethod] = {}
		for country, method in mapping.items():
			code = country.strip().upper()
			if len(code) != 2 or not code.isascii() or not code.isalpha():
				raise ValueError(f"invalid country code: {country}")
			if method is CalculationMethod.AUTO:
				raise ValueError("country map cannot select AUTO")
			if code in normalized:
				raise ValueError(f"duplicate country code: {code}")
			normalized[code] = method
		self._mapping = MappingProxyType(normalized)
		self._fallback = fallback

	def resolve(self, country_code: str) -> CalculationMethod:
		code = country_code.strip().upper()
		if len(code) != 2 or not code.isascii() or not code.isalpha():
			raise ValueError("country_code must be a two-letter ISO code")
		return self._mapping.get(code, self._fallback)


class PrayerCalculator:
	"""Calculate six prayer events without platform, config, file, or network access."""

	def calculate(self, request: PrayerCalculationRequest, definition: CalculationMethodDefinition,
			timezone: tzinfo, *, effective_method: CalculationMethod) -> PrayerTimes:
		if definition.code is not effective_method:
			raise ValueError("method definition does not match the effective method")
		fallback_latitude: float | None = None
		raw = self._calculate_hours(request.local_date, request.latitude, request.longitude,
			request.asr_method, definition)
		polar = raw[PrayerName.SUNRISE] is None or raw[PrayerName.MAGHRIB] is None
		if polar or request.high_latitude_rule is HighLatitudeRule.NEAREST_LATITUDE:
			fallback_latitude = math.copysign(NEAREST_LATITUDE, request.latitude or 1.0)
			raw = self._calculate_hours(request.local_date, fallback_latitude, request.longitude,
				request.asr_method, definition)
		if raw[PrayerName.SUNRISE] is None or raw[PrayerName.MAGHRIB] is None:
			raise PrayerCalculationError("sunrise and sunset are unavailable after nearest-latitude fallback")

		effective_high_rule: HighLatitudeRule | None = None
		angle_based_used = False
		if request.high_latitude_rule is not HighLatitudeRule.NEAREST_LATITUDE:
			effective_high_rule, angle_based_used = self._adjust_high_latitudes(
				raw, request.high_latitude_rule, definition)
			if effective_high_rule is None and fallback_latitude is not None:
				effective_high_rule = HighLatitudeRule.NEAREST_LATITUDE
		elif fallback_latitude is not None:
			effective_high_rule = HighLatitudeRule.NEAREST_LATITUDE

		method_offsets = {prayer.value: 0 for prayer in PrayerName}
		method_offsets[PrayerName.MAGHRIB.value] = definition.maghrib_offset_minutes
		assert raw[PrayerName.MAGHRIB] is not None
		raw[PrayerName.MAGHRIB] += definition.maghrib_offset_minutes / 60

		isha_interval: int | None = None
		if definition.isha_interval_minutes is not None:
			if definition.isha_ramadan_interval_minutes is not None:
				if request.is_ramadan is None:
					raise RamadanContextRequired(
						f"{effective_method.value} requires explicit Ramadan context to choose its Isha interval")
				isha_interval = (definition.isha_ramadan_interval_minutes if request.is_ramadan
					else definition.isha_interval_minutes)
			else:
				isha_interval = definition.isha_interval_minutes
			raw[PrayerName.ISHA] = raw[PrayerName.MAGHRIB] + isha_interval / 60
			method_offsets[PrayerName.ISHA.value] = isha_interval

		base_utc = datetime.combine(request.local_date, time(), tzinfo=_UTC)
		values: dict[PrayerName, datetime] = {}
		corrections = request.corrections.as_mapping()
		for prayer in PrayerName:
			hours = raw[prayer]
			if hours is None or not math.isfinite(hours):
				raise PrayerCalculationError(f"{prayer.value} is unavailable under the requested policy")
			moment = base_utc + timedelta(hours=hours, minutes=corrections[prayer.value])
			values[prayer] = self._round_minute(moment.astimezone(timezone))

		metadata = PrayerCalculationMetadata(
			requested_method=request.calculation_method, effective_method=effective_method,
			asr_method=request.asr_method, timezone_id=request.timezone_id,
			requested_high_latitude_rule=request.high_latitude_rule,
			effective_high_latitude_rule=effective_high_rule, angle_based_used=angle_based_used,
			high_latitude_fallback_used=fallback_latitude is not None,
			fallback_latitude=fallback_latitude,
			method_offsets_minutes=MappingProxyType(method_offsets),
			user_corrections_minutes=corrections, isha_interval_minutes=isha_interval,
			is_ramadan=request.is_ramadan)
		return PrayerTimes(**{prayer.value: values[prayer] for prayer in PrayerName}, metadata=metadata)

	def _calculate_hours(self, day: date, latitude: float, longitude: float, asr_method: AsrMethod,
			definition: CalculationMethodDefinition) -> dict[PrayerName, float | None]:
		julian = self._julian_day(day.year, day.month, day.day) - longitude / 360
		hours: dict[PrayerName, float | None] = {
			PrayerName.FAJR: 5, PrayerName.SUNRISE: 6, PrayerName.DHUHR: 12,
			PrayerName.ASR: 13, PrayerName.MAGHRIB: 18, PrayerName.ISHA: 18}
		for _ in range(2):
			parts = {name: (value if value is not None else 12) / 24 for name, value in hours.items()}
			hours = {
				PrayerName.FAJR: self._sun_angle_time(julian, latitude, definition.fajr_angle, parts[PrayerName.FAJR], True),
				PrayerName.SUNRISE: self._sun_angle_time(julian, latitude, SUNRISE_SUNSET_ANGLE, parts[PrayerName.SUNRISE], True),
				PrayerName.DHUHR: self._midday(julian, parts[PrayerName.DHUHR]),
				PrayerName.ASR: self._asr_time(julian, latitude, 1 if asr_method is AsrMethod.STANDARD else 2, parts[PrayerName.ASR]),
				PrayerName.MAGHRIB: self._sun_angle_time(julian, latitude, SUNRISE_SUNSET_ANGLE, parts[PrayerName.MAGHRIB], False),
				PrayerName.ISHA: (self._sun_angle_time(julian, latitude, definition.isha_angle, parts[PrayerName.ISHA], False)
					if definition.isha_angle is not None else None)}
		adjustment = -longitude / 15
		return {name: value + adjustment if value is not None else None for name, value in hours.items()}

	def _adjust_high_latitudes(self, hours: dict[PrayerName, float | None], rule: HighLatitudeRule,
			definition: CalculationMethodDefinition) -> tuple[HighLatitudeRule | None, bool]:
		sunrise, sunset = hours[PrayerName.SUNRISE], hours[PrayerName.MAGHRIB]
		assert sunrise is not None and sunset is not None
		night = (sunrise + 24 - sunset) % 24
		selected = HighLatitudeRule.ANGLE_BASED if rule is HighLatitudeRule.AUTO else rule
		used = False
		for prayer, angle, before in ((PrayerName.FAJR, definition.fajr_angle, True),
				(PrayerName.ISHA, definition.isha_angle, False)):
			if angle is None:
				continue
			portion = self._night_portion(selected, angle, night)
			value = hours[prayer]
			difference = ((sunrise - value) % 24) if before and value is not None else (
				((value - sunset) % 24) if value is not None else math.inf)
			if value is None or (rule is not HighLatitudeRule.AUTO and difference > portion):
				hours[prayer] = sunrise - portion if before else sunset + portion
				used = True
		return (selected if used else None, selected is HighLatitudeRule.ANGLE_BASED and used)

	@staticmethod
	def _night_portion(rule: HighLatitudeRule, angle: float, night: float) -> float:
		if rule is HighLatitudeRule.ANGLE_BASED:
			return angle / 60 * night
		if rule is HighLatitudeRule.ONE_SEVENTH:
			return night / 7
		if rule is HighLatitudeRule.NIGHT_MIDDLE:
			return night / 2
		raise PrayerCalculationError("nearest latitude must be applied before night-portion adjustment")

	@staticmethod
	def _sun_position(julian: float) -> tuple[float, float]:
		days = julian - 2451545.0
		g = _fix_angle(357.529 + 0.98560028 * days)
		q = _fix_angle(280.459 + 0.98564736 * days)
		longitude = _fix_angle(q + 1.915 * _sin(g) + 0.020 * _sin(2 * g))
		obliquity = 23.439 - 0.00000036 * days
		ra = _fix_hour(_atan2(_cos(obliquity) * _sin(longitude), _cos(longitude)) / 15)
		return _asin(_sin(obliquity) * _sin(longitude)), q / 15 - ra

	@classmethod
	def _midday(cls, julian: float, portion: float) -> float:
		return _fix_hour(12 - cls._sun_position(julian + portion)[1])

	@classmethod
	def _sun_angle_time(cls, julian: float, latitude: float, angle: float,
			portion: float, before: bool) -> float | None:
		declination = cls._sun_position(julian + portion)[0]
		noon = cls._midday(julian, portion)
		denominator = _cos(declination) * _cos(latitude)
		if abs(denominator) < 1e-15:
			return None
		ratio = (-_sin(angle) - _sin(declination) * _sin(latitude)) / denominator
		if not -1 <= ratio <= 1:
			return None
		delta = _acos(ratio) / 15
		return noon - delta if before else noon + delta

	@classmethod
	def _asr_time(cls, julian: float, latitude: float, factor: int, portion: float) -> float | None:
		declination = cls._sun_position(julian + portion)[0]
		angle = -_acot(factor + _tan(abs(latitude - declination)))
		return cls._sun_angle_time(julian, latitude, angle, portion, False)

	@staticmethod
	def _julian_day(year: int, month: int, day: int) -> float:
		if month <= 2:
			year -= 1
			month += 12
		century = year // 100
		correction = 2 - century + century // 4
		return math.floor(365.25 * (year + 4716)) + math.floor(30.6001 * (month + 1)) + day + correction - 1524.5

	@staticmethod
	def _round_minute(value: datetime) -> datetime:
		return (value + timedelta(seconds=30)).replace(second=0, microsecond=0)


class _Utc(tzinfo):
	def utcoffset(self, dt: datetime | None) -> timedelta:
		return timedelta(0)

	def dst(self, dt: datetime | None) -> timedelta:
		return timedelta(0)

	def tzname(self, dt: datetime | None) -> str:
		return "UTC"


_UTC = _Utc()


def _fix_angle(value: float) -> float:
	return value - 360 * math.floor(value / 360)


def _fix_hour(value: float) -> float:
	return value - 24 * math.floor(value / 24)


def _sin(value: float) -> float:
	return math.sin(math.radians(value))


def _cos(value: float) -> float:
	return math.cos(math.radians(value))


def _tan(value: float) -> float:
	return math.tan(math.radians(value))


def _asin(value: float) -> float:
	return math.degrees(math.asin(value))


def _acos(value: float) -> float:
	return math.degrees(math.acos(value))


def _atan2(y: float, x: float) -> float:
	return math.degrees(math.atan2(y, x))


def _acot(value: float) -> float:
	return math.degrees(math.atan2(1, value))
