"""Arabic and English Qibla descriptions without translation in Domain."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..domain.qibla import QiblaDirection, QiblaResult


@runtime_checkable
class QiblaFormatter(Protocol):
	language: str

	def format(self, result: QiblaResult) -> str:
		...


class ArabicQiblaFormatter:
	language = "ar"
	_NAMES = {
		QiblaDirection.NORTH: "الشمال",
		QiblaDirection.EAST: "الشرق",
		QiblaDirection.SOUTH: "الجنوب",
		QiblaDirection.WEST: "الغرب",
	}

	def format(self, result: QiblaResult) -> str:
		direction = self._NAMES[result.direction]
		bearing = _one_decimal(result.bearing_degrees)
		if result.lean_direction is None:
			return f"اتجاه القبلة نحو {direction}؛ أي ما يعادل {bearing} درجة من الشمال الحقيقي."
		lean = self._NAMES[result.lean_direction]
		return (
			f"اتجاه القبلة نحو {direction}، مع الميل إلى {lean} بمقدار "
			f"{_one_decimal(result.lean_degrees)} درجة؛ أي ما يعادل {bearing} درجة من الشمال الحقيقي."
		)


class EnglishQiblaFormatter:
	language = "en"
	_NAMES = {
		QiblaDirection.NORTH: "north",
		QiblaDirection.EAST: "east",
		QiblaDirection.SOUTH: "south",
		QiblaDirection.WEST: "west",
	}

	def format(self, result: QiblaResult) -> str:
		direction = self._NAMES[result.direction]
		bearing = _one_decimal(result.bearing_degrees)
		if result.lean_direction is None:
			return f"The Qibla is toward {direction}; {bearing} degrees clockwise from true north."
		lean = self._NAMES[result.lean_direction]
		return (
			f"The Qibla is toward {direction}, leaning {result.lean_degrees:.1f} degrees "
			f"toward {lean}; {bearing} degrees clockwise from true north."
		)


def _one_decimal(value: float) -> str:
	return f"{value:.1f}"
