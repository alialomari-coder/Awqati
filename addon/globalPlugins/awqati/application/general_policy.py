"""Pure general policies owned by settings task 3.2."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from enum import Enum

from ..domain import AwqatiSettings, ClockTime, Location, QuietHoursSettings


LOCATION_REQUIRED_MESSAGE = "لم يتم تعيين الموقع. فضلًا عيّنه من إعدادات أوقاتي ثم حاول مرة أخرى"


class AutomaticAlertKind(Enum):
	"""The distinction needed by quiet hours before the scheduler exists."""

	PRAYER = "prayer"
	OTHER = "other"


@dataclass(frozen=True, slots=True)
class AlertPolicyDecision:
	deliver: bool
	suppressed_by_global_switch: bool = False
	suppressed_by_quiet_hours: bool = False


def first_run_location_required(settings: AwqatiSettings) -> bool:
	"""Use validity of the persisted location as the sole first-run criterion."""

	return settings.location is None


def location_requirement_message(location: Location | None) -> str | None:
	"""Return the approved user-facing refusal and never invent coordinates."""

	return LOCATION_REQUIRED_MESSAGE if location is None else None


def manual_commands_allowed() -> bool:
	"""Manual commands are outside every automatic-alert suppression layer."""

	return True


def _minutes(value: ClockTime | time) -> int:
	return value.hour * 60 + value.minute


def is_quiet_time(local_time: time, settings: QuietHoursSettings) -> bool:
	"""Use a start-inclusive, end-exclusive local-time interval."""

	if not settings.enabled:
		return False
	current = _minutes(local_time)
	start = _minutes(settings.start)
	end = _minutes(settings.end)
	if start == end:
		return False
	if start < end:
		return start <= current < end
	return current >= start or current < end


def automatic_alert_policy(
	settings: AwqatiSettings,
	kind: AutomaticAlertKind,
	local_time: time,
) -> AlertPolicyDecision:
	"""Decide suppression without changing an event or scheduling catch-up."""

	if not settings.general.all_automatic_alerts_enabled:
		return AlertPolicyDecision(False, suppressed_by_global_switch=True)
	quiet = settings.general.quiet_hours
	quiet_applies = kind is AutomaticAlertKind.OTHER or quiet.apply_to_prayer_alerts
	if quiet_applies and is_quiet_time(local_time, quiet):
		return AlertPolicyDecision(False, suppressed_by_quiet_hours=True)
	return AlertPolicyDecision(True)
