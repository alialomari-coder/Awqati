"""Opt-in task 3.1 wording; never invoked by the current synopsis."""
import math


def format_lunar_distance_thousands(distance_km: float) -> str:
    """Nearest thousand km, positive halfway values rounded upward."""
    if not math.isfinite(distance_km) or distance_km <= 0:
        raise ValueError("distance_km must be finite and positive")
    return str(math.floor(distance_km / 1000 + .5))


def format_lunar_distance(distance_km: float, language: str) -> str:
    """Arabic/English speech text, with no grouping or decimal separators."""
    value = format_lunar_distance_thousands(distance_km)
    if language == "ar":
        return f"ويبعد القمر حاليًا عن الأرض نحو {value} ألف كيلومتر"
    if language == "en":
        return f"And the Moon is currently about {value} thousand kilometers from Earth"
    raise ValueError("language must be ar or en")
