"""Translatable countdown states shared by UI and commands."""
from .stopwatch_formatter import spoken as _spoken

N_ = lambda message: message
STATE_LABELS = {"ready": N_("Ready"), "running": N_("Running"), "paused": N_("Paused"), "finished": N_("Finished"), "cancelled": N_("Cancelled")}


def spoken(ns, translate):
    """Countdown queries use whole seconds, avoiding noisy milliseconds."""
    return _spoken(((max(0, int(ns)) + 999999999) // 10**9) * 10**9, translate)
