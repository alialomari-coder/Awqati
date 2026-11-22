"""Present extracted records without fetching or reparsing Wikipedia HTML."""

from ..domain.on_this_day import Failure, OnThisDayError


def N_(text):
    return text


LABELS = {
    "events": N_("Historical events"), "births": N_("Births"),
    "deaths": N_("Deaths"), "observances": N_("Holidays and observances"),
}
ERRORS = {
    Failure.UNAVAILABLE: N_("Information is unavailable in the selected language."),
    Failure.CONNECTION: N_("Could not connect to Wikipedia. Check your connection and try again."),
    Failure.SERVER: N_("Wikipedia's server could not provide the information. Try again later."),
    Failure.RATE_LIMIT: N_("Wikipedia's request limit was reached. Try again later."),
    Failure.ACCESS: N_("Wikipedia denied access to the information."),
    Failure.API: N_("Wikipedia could not process the request. Try again later."),
    Failure.RESPONSE: N_("Wikipedia returned an invalid response. Try again later."),
    Failure.EXTRACTION: N_("The Wikipedia section could not be read completely. No partial information will be presented."),
}


def section_tree(day, key):
    section = day.section(key)
    if section.failure:
        raise OnThisDayError(section.failure, section.detail)
    if not section.entries:
        raise OnThisDayError(Failure.UNAVAILABLE, "empty section")
    # Contexts describe the source's real nested lists, including year-only
    # parents. Reuse the immediately preceding parent, never merge distant items.
    root = []
    previous_path = []
    for entry in section.entries:
        path = [(c.text, c.links) for c in entry.context]
        siblings = root
        active = []
        for depth, value in enumerate(path):
            if depth < len(previous_path) and previous_path[depth][0] == value:
                node = previous_path[depth][1]
            elif siblings and siblings[-1][:2] == list(value):
                node = siblings[-1]
            else:
                node = [value[0], value[1], []]
                siblings.append(node)
            active.append((value, node))
            siblings = node[2]
        siblings.append([entry.text, entry.links, []])
        previous_path = active
    return root


def heading(day, key, translate):
    return translate(N_("On This Day — {date} — {section}")).format(
        date=f"{day.title}, {day.local_date.year}", section=translate(LABELS[key]))


def speech_lines(day, key, translate):
    lines = [heading(day, key, translate)]
    def walk(nodes):
        for text, links, children in nodes:
            lines.append(text)
            walk(children)
    walk(section_tree(day, key))
    return lines




class OnThisDayPresentation:
    """GUI-thread selection guard; service retains ownership of shared fetches."""
    def __init__(self, service, *, language, today, web_mode, translate, schedule,
                 settle_ms, speak, stop_speech, message, open_page):
        self.service = service
        self.language, self.today, self.web_mode = language, today, web_mode
        self.translate, self.schedule, self.settle_ms = translate, schedule, settle_ms
        self.speak, self.stop_speech, self.message, self.open_page = speak, stop_speech, message, open_page
        self.generation = 0
        self.closed = False
        self.timer = None
        self.wait_timer = None
        self.wait_identity = None

    def select(self, key, *, force_web=False):
        self.generation += 1
        generation = self.generation
        if self.closed:
            return
        self.stop_speech()
        if self.wait_timer:
            self.wait_timer.Stop()
            self.wait_timer = None
        if self.timer:
            self.timer.Stop()
            self.timer = None
        identity = (self.today(), self.language(), True if force_web else self.web_mode())
        settled = not identity[2]
        result = None
        delivered = False
        def valid():
            return (not self.closed and generation == self.generation
                    and identity == (self.today(), self.language(), True if force_web else self.web_mode()))
        def deliver():
            nonlocal delivered
            if not valid() or not settled or result is None or delivered:
                return
            delivered = True
            try:
                if isinstance(result, OnThisDayError):
                    raise result
                if (result.local_date, result.language) != identity[:2]:
                    return
                if identity[2]:
                    self.open_page(result, key, self.translate)
                else:
                    self.speak(speech_lines(result, key, self.translate))
            except OnThisDayError as error:
                if error.kind not in {Failure.STALE, Failure.CANCELLED}:
                    self.message(self.translate(ERRORS.get(error.kind, ERRORS[Failure.RESPONSE])))
            except OSError:
                self.message(self.translate(N_("Could not create or open the local On This Day web page.")))
        def received(value):
            nonlocal result
            result = value
            if valid():
                if self.wait_timer:
                    self.wait_timer.Stop()
                    self.wait_timer = None
                self.wait_identity = None
            deliver()
        def announce_wait():
            # Fast memory/disk results remain silent, including while a ready
            # web page waits for the multi-press selection to settle.
            if valid() and result is None and self.wait_identity != identity:
                self.wait_identity = identity
                self.message(self.translate(N_("Please wait.")))
        def settle():
            nonlocal settled
            settled = True
            deliver()
        if identity[2] and not force_web:
            # Read NVDA's actual timeout, and wait beyond it after *each* press.
            self.timer = self.schedule(self.settle_ms(), settle)
        elif force_web:
            settled = True
        self.wait_timer = self.schedule(800, announce_wait)
        self.service.request(received, section=key)

    def close(self):
        self.closed = True
        self.generation += 1
        if self.timer:
            self.timer.Stop()
        if self.wait_timer:
            self.wait_timer.Stop()
        self.stop_speech()
        self.service.close()
