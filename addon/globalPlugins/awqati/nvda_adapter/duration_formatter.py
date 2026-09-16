"""Shared localized duration presentation for NVDA prayer-state messages."""

from __future__ import annotations

from typing import Callable


N_ = lambda message: message
_LANGUAGE_MARKER = N_("Duration formatting language: English")


def format_minutes(total_minutes: int, translate: Callable[[str], str], *, oblique: bool = False) -> str:
	"""Format a non-negative whole-minute duration in natural hours and minutes."""
	if isinstance(total_minutes, bool) or not isinstance(total_minutes, int) or total_minutes < 0:
		raise ValueError("total_minutes must be a non-negative integer")
	hours, minutes = divmod(total_minutes, 60)
	if translate(_LANGUAGE_MARKER) == _LANGUAGE_MARKER:
		parts = []
		if hours:
			parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
		if minutes or not parts:
			parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
		return " ".join(parts)
	parts = []
	if hours:
		parts.append(_format_arabic_unit(hours, translate, "hour", oblique))
	if minutes or not parts:
		parts.append(_format_arabic_unit(minutes, translate, "minute", oblique))
	if len(parts) == 2:
		return translate(N_("{hours} {minutes}")).format(hours=parts[0], minutes=parts[1])
	return parts[0]


def _format_arabic_unit(value: int, translate: Callable[[str], str], unit: str,
		oblique: bool) -> str:
	if unit == "hour":
		one, two, two_oblique = N_("1 hour"), N_("2 hours"), N_("2 hours after a preposition")
		plural, general = N_("{count} hours"), N_("{count} hour")
	else:
		one, two, two_oblique = N_("1 minute"), N_("2 minutes"), N_("2 minutes after a preposition")
		plural, general = N_("{count} minutes"), N_("{count} minute")
	if value == 1:
		return translate(one)
	if value == 2:
		return translate(two_oblique if oblique else two)
	template = plural if 3 <= value <= 10 else general
	return translate(template).format(count=value)