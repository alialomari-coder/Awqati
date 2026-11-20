"""Opt-in Arabic/English lunar horizon prose, reserved for task 3.1."""
from datetime import datetime, timezone
from typing import Callable

from ..domain.lunar_horizon import LunarEventState, LunarHorizonEvents


def format_lunar_horizon(events: LunarHorizonEvents, language: str,
                         format_time: Callable[[datetime], str]) -> str:
    """Use the caller's accessible clock format; keep all repeated events.

    On multiple events attach each numeric UTC offset to disambiguate folds.
    Name the Moon at first mention; narrate events in absolute time order.
    No rounding or event selection occurs in this presentation layer.
    """
    if language not in ('ar', 'en'):
        raise ValueError('language must be ar or en')
    arabic = language == 'ar'
    parts = []
    timed = []
    notes = []
    for rise, values, state in (
        (True, events.rises_local, events.rise_state),
        (False, events.sets_local, events.set_state),
    ):
        if state is LunarEventState.CALCULATION_ERROR:
            notes.append(('تعذر حساب شروق القمر اليوم' if rise else 'تعذر حساب غروب القمر اليوم') if arabic
                         else ('Moonrise could not be calculated today' if rise else 'Moonset could not be calculated today'))
        elif not values:
            notes.append(('لا يشرق القمر خلال اليوم' if rise else 'لا يغرب القمر خلال اليوم') if arabic
                         else ('The Moon does not rise today' if rise else 'The Moon does not set today'))
        else:
            timed.extend((t, rise, len(values) > 1) for t in values)
    # UTC ordering also handles repeated wall times during civil-time folds.
    for t, rise, multiple in sorted(timed, key=lambda item: item[0].astimezone(timezone.utc)):
        value = format_time(t)
        offset = f' (UTC{t:%z})'
        if multiple and offset not in value:
            value += offset
        if arabic:
            verb = 'يشرق' if rise else 'يغرب'
            if not parts:
                verb += ' القمر اليوم'
            parts.append(verb + ' عند الساعة ' + value)
        else:
            verb = 'rises' if rise else 'sets'
            if not parts:
                verb = 'The Moon ' + verb + ' today'
            parts.append(verb + ' at ' + value)
    parts.extend(notes)
    return ('، و' if arabic else ', and ').join(parts) + '.'
