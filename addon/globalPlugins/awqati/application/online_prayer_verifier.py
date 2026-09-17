"""Compare six internal prayer times with an optional online provider."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Mapping, Protocol

from ..domain import AsrMethod, CalculationMethod, HighLatitudeRule, PrayerName, PrayerTimes
from .operation import CancellationToken


class OnlinePrayerVerificationError(RuntimeError):
	"""The provider response could not be obtained or validated."""


@dataclass(frozen=True, slots=True)
class OnlinePrayerRequest:
	local_date: date
	latitude: float
	longitude: float
	calculation_method: CalculationMethod
	asr_method: AsrMethod
	high_latitude_rule: HighLatitudeRule


class OnlinePrayerProvider(Protocol):
	def fetch(self, request: OnlinePrayerRequest, *, timeout: float,
			cancellation: CancellationToken) -> Mapping[PrayerName, int]: ...


@dataclass(frozen=True, slots=True)
class PrayerTimeDifference:
	prayer: PrayerName
	internal: datetime
	online_minutes: int
	difference_minutes: int


@dataclass(frozen=True, slots=True)
class PrayerVerificationResult:
	differences: tuple[PrayerTimeDifference, ...]

	@property
	def is_close(self) -> bool:
		return not self.differences


class OnlinePrayerVerifier:
	"""Perform a read-only comparison; it never mutates settings or prayer data."""

	TOLERANCE_MINUTES = 2

	def __init__(self, provider: OnlinePrayerProvider) -> None:
		self._provider = provider

	def verify(self, request: OnlinePrayerRequest, internal: PrayerTimes, *, timeout: float = 12.0,
			cancellation: CancellationToken | None = None) -> PrayerVerificationResult:
		token = cancellation or CancellationToken()
		token.raise_if_cancelled()
		try:
			online = self._provider.fetch(request, timeout=timeout, cancellation=token)
		except OnlinePrayerVerificationError:
			raise
		except Exception as error:
			raise OnlinePrayerVerificationError(str(error)) from error
		token.raise_if_cancelled()
		if set(online) != set(PrayerName):
			raise OnlinePrayerVerificationError("provider response must contain exactly the six prayer times")
		differences = []
		for prayer in PrayerName:
			value = online[prayer]
			if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value < 1440:
				raise OnlinePrayerVerificationError(f"invalid online time for {prayer.value}")
			internal_time = getattr(internal, prayer.value)
			internal_minutes = internal_time.hour * 60 + internal_time.minute
			raw = abs(internal_minutes - value)
			difference = min(raw, 1440 - raw)
			if difference > self.TOLERANCE_MINUTES:
				differences.append(PrayerTimeDifference(prayer, internal_time, value, difference))
		return PrayerVerificationResult(tuple(differences))
