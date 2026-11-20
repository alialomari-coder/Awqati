"""Optional task 3.1 wording; not connected to the current synopsis."""
from datetime import datetime, tzinfo
from typing import Callable
from ..domain.lunar_phases import LunarPhaseEvent, PrincipalPhase

_NAMES = {
    "ar": ("المحاق", "التربيع الأول", "البدر", "التربيع الأخير"),
    "en": ("new moon", "first quarter", "full moon", "last quarter"),
}


def format_next_lunar_phase(event: LunarPhaseEvent | None, zone: tzinfo,
                           language: str, format_date: Callable[[datetime], str],
                           format_time: Callable[[datetime], str], *, mention_moon: bool = True,
                           connective: bool = True) -> str:
    """Callbacks use the existing date/clock preferences, at the event's zone.

    Date is always stated, so local midnight/year rollover remains explicit.
    No location-dependent astronomy or selection in the formatter.
    """
    if language not in _NAMES:
        raise ValueError("language must be ar or en")
    if event is None:
        return ("لا يتوفر طور قمري قادم ضمن النطاق الزمني المعتمد." if language == "ar"
                else "No upcoming lunar phase is available within the supported range.")
    name = _NAMES[language][tuple(PrincipalPhase).index(event.phase)]
    local = event.local_time(zone)
    day, clock = format_date(local), format_time(local)
    if language == "ar":
        if event.phase is PrincipalPhase.NEW_MOON:
            return f"{'و' if connective else ''}يحدث المحاق القادم يوم {day}، عند الساعة {clock}."
        subject = " القمر" if mention_moon else ""
        return f"{'و' if connective else ''}سيبلغ{subject} طور {name} يوم {day}، عند الساعة {clock}."
    if event.phase is PrincipalPhase.NEW_MOON:
        return f"{'And the' if connective else 'The'} next new moon occurs on {day} at {clock}."
    subject = "the Moon" if mention_moon else "it"
    start = f"And {subject}" if connective else ("The Moon" if mention_moon else "It")
    return f"{start} reaches {name} on {day} at {clock}."
