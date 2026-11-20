"""Task 3.1 prose composed from approved calculation results only."""
from datetime import timedelta, timezone
import math

from ..domain.astronomy import Season, SolarTransitState, SolarDayState
from ..domain.lunar_transit import LunarTransitState, MaximumKind
from ..domain.lunar_horizon import LunarEventState
from .lunar_distance_presentation import format_lunar_distance_thousands
from ..domain.lunar_phases import PrincipalPhase
from .lunar_horizon_presentation import format_lunar_horizon
from .lunar_phases_presentation import format_next_lunar_phase
from .sun_distance_presentation import format_sun_distance_millions


def additional_solar(reading, language, clock, duration):
    ar = language == 'ar'
    facts = reading.daily_details
    parts = []
    solar = reading.solar_day
    ordinary = (solar.state is SolarDayState.NORMAL and reading.sunrise_local is not None
                and reading.sunset_local is not None)
    if ordinary:
        parts.append((f'تشرق الشمس اليوم عند الساعة {clock(reading.sunrise_local)}، وتغرب عند الساعة {clock(reading.sunset_local)}'
                      if ar else f'The Sun rises today at {clock(reading.sunrise_local)} and sets at {clock(reading.sunset_local)}'))
    elif solar.state is SolarDayState.NORMAL:
        parts.append('لا تتوفر أوقات شروق الشمس وغروبها اليوم.' if ar else 'Sunrise and sunset times are unavailable today.')
    if (solar.transit_state is SolarTransitState.AVAILABLE and reading.solar_transit_local is not None
            and solar.transit_altitude_degrees is not None and math.isfinite(solar.transit_altitude_degrees)):
        altitude = _angle(solar.transit_altitude_degrees)
        if ar:
            subject = 'وتعبر' if ordinary else 'وتعبر الشمس'
            transit = f'{subject} خط الزوال عند الساعة {clock(reading.solar_transit_local)}، بارتفاع قدره {altitude} درجة عن الأفق.'
        else:
            subject = 'Its upper meridian transit is' if ordinary else 'The Sun makes its upper meridian transit'
            transit = f'{subject} at {clock(reading.solar_transit_local)}, at an altitude of {altitude} degrees above the horizon.'
        if ordinary and ar:
            parts[-1] += '، ' + transit
        else:
            if ordinary:
                parts[-1] += '.'
            parts.append(transit)
    else:
        if ordinary:
            parts[-1] += '.'
        parts.append('لا يتوفر عبور زوالي علوي محدد للشمس اليوم.' if ar else 'No definite upper meridian transit of the Sun is available today.')
    try:
        value = format_sun_distance_millions(facts.sun_distance.distance_km) if facts.sun_distance else None
    except ValueError:
        value = None
    parts.append((f'وتبعد الأرض عنها حاليًا نحو {value} مليون كيلومتر.' if ar else f'Earth is currently about {value} million kilometers from the Sun.') if value else
                 ('تعذر حساب المسافة الشمسية الحالية.' if ar else 'The current solar distance could not be calculated.'))
    return ' '.join(parts)


def daylight_context(reading, language, duration):
    """Keep the solstice comparison and annual extremes with day length."""
    ar = language == 'ar'
    facts = reading.daily_details
    parts = []
    if facts.daylight is not None:
        d = facts.daylight
        if d.change is not None:
            reference = ('الصيفي' if d.reference_season is Season.SUMMER else 'الشتوي') if ar else ('summer' if d.reference_season is Season.SUMMER else 'winter')
            minutes = round(abs(d.change.total_seconds()) / 60)
            if minutes == 0:
                parts.append(f'لم يتغير طول النهار تغيرًا ملحوظًا منذ الانقلاب {reference} الأخير.' if ar else f'Daylight is effectively unchanged since the last {reference} solstice.')
            else:
                direction = ('اكتسبه' if d.change > timedelta(0) else 'فقده') if ar else ('gained' if d.change > timedelta(0) else 'lost')
                value = duration(abs(d.change))
                if ar:
                    value = value.replace('ساعتان', 'ساعتين').replace('دقيقتان', 'دقيقتين')
                parts.append(f'بلغ مجموع ما {direction} من طوله منذ الانقلاب {reference} الأخير {value}.' if ar else f'has {direction} a total of {value} since the last {reference} solstice.')
        else:
            parts.append('لا تتوفر مقارنة لطول النهار مع الانقلاب الأخير.' if ar else 'A daylight comparison with the reference solstice is unavailable.')
        # Night dates come from actual sunset-to-next-sunrise durations, not
        # from assuming that the longest day has the shortest night.
        names = []
        for key, arabic, english in (
            ('longestDay', 'أطول نهار', 'the longest day'),
            ('shortestDay', 'أقصر نهار', 'the shortest day'),
        ):
            if key in d.events_today:
                names.append(arabic if ar else english)
        for dates, arabic, english in (
            (d.annual.longest_night_dates, 'أطول ليل', 'the longest night'),
            (d.annual.shortest_night_dates, 'أقصر ليل', 'the shortest night'),
        ):
            if reading.local_date in dates:
                names.append(arabic if ar else english)
        if names:
            parts.append(('ويوافق اليوم ' + ' و'.join(names) + ' خلال السنة.' if ar else 'Today has ' + ' and '.join(names) + ' of the year.'))
    else:
        parts.append('تعذر حساب تغير طول النهار والأيام القصوى.' if ar else 'Daylight change and annual extremes could not be calculated.')
    return ' '.join(parts)


def additional_lunar(reading, language, clock, date):
    ar = language == 'ar'
    facts = reading.daily_details
    ordinary = _ordinary_lunar_events(facts, language, clock)
    if ordinary is not None:
        return ordinary
    parts = [format_lunar_horizon(facts.horizon, language, clock) if facts.horizon else
             ('تعذر حساب شروق القمر وغروبه اليوم.' if ar else 'Moonrise and moonset could not be calculated today.')]
    transit = facts.transit
    if transit is None:
        parts.append('تعذر حساب العبور القمري وأعلى ارتفاع اليوم.' if ar else 'Lunar transit and greatest altitude could not be calculated today.')
    else:
        if transit.transit_state in (LunarTransitState.AVAILABLE, LunarTransitState.MULTIPLE) and transit.transits:
            for p in transit.transits:
                if math.isfinite(p.altitude_degrees):
                    parts.append(f'ويعبر خط الزوال عند الساعة {clock(p.at_utc.astimezone(transit.zone))}.' if ar else f'Its upper meridian transit is at {clock(p.at_utc.astimezone(transit.zone))}.')
        else:
            notes = {
                LunarTransitState.NO_EVENT: ('لا يحدث عبور زوالي علوي للقمر خلال اليوم.', 'The Moon has no upper meridian transit today.'),
                LunarTransitState.UNDEFINED_MERIDIAN: ('لا يُعرّف عبور زوالي قمري فريد عند القطب الجغرافي.', 'A unique lunar meridian transit is undefined at the geographic pole.'),
            }
            parts.append(notes.get(transit.transit_state, ('تعذر حساب العبور القمري اليوم.', 'Lunar transit could not be calculated today.'))[0 if ar else 1])
        maximum_available = transit.maximum_state in (LunarEventState.AVAILABLE, LunarEventState.MULTIPLE)
        if maximum_available and transit.center_below_horizon_all_day:
            parts.append('يبقى مركز القمر تحت الأفق طوال اليوم.' if ar else 'The Moon’s center remains below the horizon throughout the day.')
        valid_maxima = [p for p in transit.maxima if math.isfinite(p.altitude_degrees)] if maximum_available else []
        if not valid_maxima:
            parts.append('لا تتوفر قيمة لأعلى ارتفاع قمري اليوم.' if ar else 'No greatest lunar altitude is available today.')
        for p in valid_maxima:
            altitude = _angle(p.altitude_degrees)
            if p.kind is MaximumKind.DAY_START:
                parts.append(f'أعلى قيمة لارتفاع مركز القمر خلال اليوم تقع عند بداية اليوم المدني: {altitude} درجة بالنسبة إلى الأفق.' if ar else f'The greatest value of the Moon’s center altitude during the civil day occurs at its start: {altitude} degrees relative to the horizon.')
            elif p.kind is MaximumKind.DAY_END_LIMIT:
                parts.append(f'القيمة الحدية العظمى لارتفاع مركز القمر هي {altitude} درجة عند الاقتراب من نهاية اليوم المدني؛ وليست قمة داخلية حدثت خلال اليوم.' if ar else f'The supremum of the Moon’s center altitude is {altitude} degrees as the civil day approaches its end; it is not an interior maximum attained during the day.')
            else:
                time = clock(p.at_utc.astimezone(transit.zone))
                if p.altitude_degrees < 0:
                    parts.append(f'ويبلغ أعلى ارتفاع هندسي له عند الساعة {time}، بقيمة {altitude} درجة بالنسبة إلى الأفق.' if ar else f'Its greatest geometric altitude is at {time}, at {altitude} degrees relative to the horizon.')
                else:
                    parts.append(f'ويبلغ أعلى ارتفاع له اليوم عند الساعة {time}، بزاوية قدرها {altitude} درجة عن الأفق.' if ar else f'It reaches its greatest altitude today at {time}, at {altitude} degrees above the horizon.')
    return ' '.join(parts)


def phase_schedule(reading, language, clock, date):
    """Narrate actual UTC order; omit the year only within the current year."""
    ar = language == 'ar'
    facts = reading.daily_details
    parts = []
    if facts.phases is None:
        parts.append('تعذر حساب مواعيد الأطوار القادمة ضمن النطاق المعتمد.' if ar else 'Upcoming phase times could not be calculated within the supported range.')
    elif not facts.phases.events:
        parts.append(format_next_lunar_phase(None, facts.phases.zone, language, date, lambda value: clock(value, False)))
    else:
        # One next event per type, from a single source; never also show the
        # legacy new/full moon timestamps carried by the base reading.
        names = {
            PrincipalPhase.NEW_MOON: ('المحاق', 'new moon'),
            PrincipalPhase.FIRST_QUARTER: ('التربيع الأول', 'first quarter'),
            PrincipalPhase.FULL_MOON: ('البدر', 'full moon'),
            PrincipalPhase.LAST_QUARTER: ('التربيع الأخير', 'last quarter'),
        }
        events = sorted(facts.phases.events, key=lambda event: event.at_utc)
        previous = None
        for index, event in enumerate(events):
            name = names[event.phase][0 if ar else 1]
            local = event.local_time(facts.phases.zone)
            day = date(local, reference_year=reading.local_date.year)
            time = clock(local, False)
            if index == 0:
                if ar:
                    start = 'ويحدث المحاق القادم' if event.phase is PrincipalPhase.NEW_MOON else f'وسيبلغ القمر طور {name}'
                    parts.append(f'{start} يوم {day}، عند الساعة {time}')
                else:
                    if event.phase is PrincipalPhase.NEW_MOON:
                        start = 'The next new moon occurs'
                    elif event.phase is PrincipalPhase.FULL_MOON:
                        start = 'The next full moon is'
                    else:
                        start = f'The Moon reaches {name}'
                    parts.append(f'{start} on {day} at {time}')
            else:
                # A neutral conjunction handles coincident supplied instants;
                # never introduce succession based on rounded wall times.
                successive = event.at_utc > previous.at_utc
                if ar:
                    link = ('يليه ' if index == 1 else 'ثم ' if index == 2 else 'ف') if successive else 'و'
                    parts.append(f'، {link}{name} يوم {day}، عند الساعة {time}')
                else:
                    link = ('followed by ' if index == 1 else 'then ' if index == 2 else 'and ') if successive else 'and '
                    parts.append(f', {link}{name} on {day} at {time}')
            previous = event
        parts = [''.join(parts) + '.']
        if any(event.time_basis == 'modeledUT' for event in facts.phases.events):
            parts.append('مواعيد الأطوار تقريبية وتعتمد على تقدير فرق الزمن ΔT؛ ولا تمثل توقيت UTC محققًا.' if ar else 'Phase times are approximate and use modeled ΔT; they do not represent confirmed UTC.')
    return ' '.join(parts)


def lunar_distance_summary(reading, language):
    ar = language == 'ar'
    facts = reading.daily_details
    parts = []
    try:
        distance = format_lunar_distance_thousands(facts.lunar_distance.distance_km) if facts.lunar_distance else None
    except ValueError:
        distance = None
    parts.append((f'وتبلغ المسافة بين مركزي الأرض والقمر حاليًا نحو {distance} ألف كيلومتر.' if ar else
                  f'The distance between the centers of Earth and the Moon is currently about {distance} thousand kilometers.')
                 if distance else ('تعذر حساب المسافة القمرية الحالية.' if ar else 'The current lunar distance could not be calculated.'))
    return ' '.join(parts)


def _ordinary_lunar_events(facts, language, clock):
    """Compose a chronological sentence only for complete ordinary events.

    The approved, explicit absence/error/polar/boundary prose stays in the
    fallback. Sort raw instants, preserving the distinction between H=0 and
    the independently calculated altitude maximum.
    """
    h, t = facts.horizon, facts.transit
    if (h is None or t is None or h.rise_state is not LunarEventState.AVAILABLE
            or h.set_state is not LunarEventState.AVAILABLE
            or len(h.rises_utc) != 1 or len(h.sets_utc) != 1
            or t.transit_state is not LunarTransitState.AVAILABLE or len(t.transits) != 1
            or t.maximum_state is not LunarEventState.AVAILABLE or len(t.maxima) != 1):
        return None
    maximum = t.maxima[0]
    if (maximum.kind is not MaximumKind.INTERIOR or not math.isfinite(maximum.altitude_degrees)
            or maximum.altitude_degrees < 0 or not math.isfinite(t.transits[0].altitude_degrees)):
        return None
    events = sorted(((h.rises_utc[0], 'rise'), (h.sets_utc[0], 'set'),
                     (t.transits[0].at_utc, 'transit'), (maximum.at_utc, 'maximum')),
                    key=lambda event: event[0].astimezone(timezone.utc))
    ar = language == 'ar'
    parts = []
    for index, (instant, kind) in enumerate(events):
        time = clock(instant.astimezone(h.zone))
        altitude = _angle(maximum.altitude_degrees)
        if ar:
            clause = {
                'rise': f'يشرق عند الساعة {time}',
                'set': f'يغرب عند الساعة {time}',
                'transit': f'يعبر خط الزوال عند الساعة {time}',
                'maximum': f'يبلغ أعلى ارتفاع له عند الساعة {time}، بزاوية قدرها {altitude} درجة عن الأفق',
            }[kind]
            if index == 0:
                clause = clause.replace(' عند الساعة', ' اليوم عند الساعة', 1)
                parts.append('وهو ' + clause)
            else:
                after_transit = (kind == 'maximum' and events[index-1][1] == 'transit'
                                 and instant > events[index-1][0])
                parts.append(('، ثم ' if after_transit else '، و') + clause)
        else:
            clause = {
                'rise': f'rises at {time}', 'set': f'sets at {time}',
                'transit': f'makes its upper meridian transit at {time}',
                'maximum': f'reaches its greatest altitude at {time}, {altitude} degrees above the horizon',
            }[kind]
            if index == 0:
                clause = clause.replace(' at ', ' today at ', 1)
                parts.append('It ' + clause)
            else:
                after_transit = (kind == 'maximum' and events[index-1][1] == 'transit'
                                 and instant > events[index-1][0])
                link = ', then ' if after_transit else ', and ' if index == len(events)-1 else ', '
                parts.append(link + clause)
    return ''.join(parts) + '.'


def _angle(value):
    # Avoid a misleading negative zero at the speech precision.
    return f'{0.0 if abs(value) < .05 else value:.1f}'
