"""Numeric and spoken stopwatch durations without wall clock conversion."""
from .duration_formatter import format_minutes

N_ = lambda message: message
MODE_LABELS = (N_("Tones only"), N_("Speech only"), N_("Tones and speech"), N_("No confirmation sounds"))
STATE_LABELS = {"idle": N_("Not started"), "running": N_("Running"), "paused": N_("Paused")}
ACTION_LABELS = {"idle": N_("Start"), "running": N_("Pause"), "paused": N_("Resume")}
LAP_ORDINALS = (N_("first"), N_("second"), N_("third"), N_("fourth"), N_("fifth"),
    N_("sixth"), N_("seventh"), N_("eighth"), N_("ninth"), N_("tenth"))


def lap_ordinal(number, translate):
    if translate("Duration formatting language: English") != "Duration formatting language: English" and 1 <= number <= len(LAP_ORDINALS):
        return translate(LAP_ORDINALS[number - 1])
    return str(number)


def numeric(ns):
    ms = max(0, ns) // 1000000
    seconds, ms = divmod(ms, 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{ms:03d}"


def spoken(ns, translate):
    total_ms = max(0, ns) // 1000000
    minutes, remainder = divmod(total_ms, 60000)
    seconds, ms = divmod(remainder, 1000)
    ar = translate("Duration formatting language: English") != "Duration formatting language: English"
    parts = [format_minutes(minutes, translate, spell_out=True)] if minutes else []
    if seconds or not parts:
        if not ar:
            parts.append(f"{seconds} second{'s' if seconds != 1 else ''}")
        elif seconds == 1:
            parts.append("ثانية واحدة")
        elif seconds == 2:
            parts.append("ثانيتان")
        else:
            parts.append(f"{seconds} " + ("ثوانٍ" if 3 <= seconds <= 10 else "ثانية"))
    if ms:
        parts.append(f"{ms} " + ("مللي ثانية" if ar else "milliseconds"))
    return (" و" if ar else ", ").join(parts)


def results(stopwatch, translate):
    elapsed = stopwatch.elapsed_ns()
    lines = [translate(N_("Stopwatch")), translate(N_("Total elapsed: {time}.")).format(time=numeric(elapsed))]
    lines += [translate(N_("Lap {number}: {duration}. Total: {total}.")).format(
        number=lap.number, duration=numeric(lap.duration_ns), total=numeric(lap.total_ns)) for lap in stopwatch.laps]
    return "\r\n".join(lines)
