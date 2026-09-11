"""Stable time and date values shared by Awqati tests."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone, tzinfo

from awqati.domain import Instant

from .event_clock import EventClock


UTC = timezone.utc
UTC_PLUS_THREE = timezone(timedelta(hours=3), "UTC+03:00")
REFERENCE_DATE = date(2026, 1, 15)
LEAP_DAY = date(2024, 2, 29)
REFERENCE_DATETIME = datetime(2026, 1, 15, 12, 34, 56, tzinfo=UTC_PLUS_THREE)


def instant_at(value: datetime = REFERENCE_DATETIME) -> Instant:
	"""Create an Instant from an explicit, timezone-aware datetime."""
	return Instant(value)


def event_clock_at(value: datetime = REFERENCE_DATETIME) -> EventClock:
	"""Create a controllable EventClock at a known datetime."""
	return EventClock(instant_at(value))


def fixed_offset_hours(hours: int) -> tzinfo:
	"""Return a fixed offset timezone for a test that needs another offset."""
	return timezone(timedelta(hours=hours))
