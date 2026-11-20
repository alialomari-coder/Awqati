"""Opt-in numeric presentation for task 3.1; no synopsis integration yet."""
from __future__ import annotations

import math


def format_sun_distance_millions(distance_km: float) -> str:
	"""One decimal million km (100,000 km), with no thousands separator.

	Arabic and English templates are documented in the astronomy study.
	Keep the unrounded domain reading for all subsequent calculations.
	"""
	if not math.isfinite(distance_km) or distance_km <= 0:
		raise ValueError("distance_km must be finite and positive")
	return f"{distance_km / 1_000_000:.1f}"
