"""Independent stopwatch state machine; all time and storage are injected.

Integer nanoseconds avoid accumulated rounding. A restored running snapshot is
paused deliberately: time while NVDA was absent is never guessed from wall time.
"""
from dataclasses import dataclass

MAX_LAPS = 100000
MAX_NS = 10**21  # More than 30,000 years; reject unreasonable/corrupt data.


def valid_ns(value):
    if type(value) is not int or not 0 <= value <= MAX_NS:
        raise ValueError("Invalid stopwatch duration")
    return value


@dataclass(frozen=True)
class Lap:
    number: int
    duration_ns: int
    total_ns: int


class Stopwatch:
    def __init__(self, clock, repository):
        self.clock, self.repository = clock, repository
        self.state, self.accumulated_ns, self.anchor = "idle", 0, None
        self.laps = []
        self.restored_running = False
        raw = repository.load()
        if raw is not None:
            self._restore(raw)

    def _restore(self, raw):
        if type(raw) is not dict or type(raw.get("version")) is not int or raw.get("version") != 1:
            raise ValueError("Unsupported stopwatch data")
        state = raw["measurement"]["state"]
        elapsed = valid_ns(raw["measurement"]["elapsed_ns"])
        if state not in ("idle", "running", "paused"):
            raise ValueError("Invalid stopwatch state")
        rows = raw["laps"]
        if not isinstance(rows, list) or len(rows) > MAX_LAPS:
            raise ValueError("Invalid stopwatch laps")
        previous, laps = 0, []
        for number, row in enumerate(rows, 1):
            total = valid_ns(row["total_ns"])
            duration = valid_ns(row["duration_ns"])
            if type(row["number"]) is not int or row["number"] != number or total < previous or total > elapsed or duration != total - previous:
                raise ValueError("Inconsistent stopwatch lap")
            laps.append(Lap(number, duration, total))
            previous = total
        if state == "idle" and (elapsed or laps):
            raise ValueError("Idle stopwatch contains a measurement")
        self.restored_running = state == "running"
        self.state = "paused" if self.restored_running else state
        self.accumulated_ns, self.laps = elapsed, laps

    def elapsed_ns(self, instant=None):
        if self.state != "running":
            return self.accumulated_ns
        now = self.clock() if instant is None else instant
        return valid_ns(self.accumulated_ns + max(0, now - self.anchor))

    def _save(self, state, elapsed, laps):
        self.repository.save({"version": 1,
            "measurement": {"state": state, "elapsed_ns": elapsed},
            "laps": [dict(number=lap.number, duration_ns=lap.duration_ns, total_ns=lap.total_ns) for lap in laps]})

    def current_lap_ns(self):
        """Read the unfinished lap without saving or changing its boundary."""
        return self.elapsed_ns() - (self.laps[-1].total_ns if self.laps else 0)

    def toggle(self):
        now = self.clock()  # Capture before storage or any output.
        if self.state == "running":
            elapsed = self.elapsed_ns(now)
            self._save("paused", elapsed, self.laps)
            self.state, self.accumulated_ns, self.anchor = "paused", elapsed, None
            return "pause"
        action = "start" if self.state == "idle" else "resume"
        self._save("running", self.accumulated_ns, self.laps)
        self.state, self.anchor = "running", now
        return action

    def record_lap(self):
        if self.state != "running":
            raise ValueError("A lap requires a running stopwatch")
        total = self.elapsed_ns()  # Capture before storage and feedback.
        if len(self.laps) >= MAX_LAPS:
            raise ValueError("The stopwatch lap safety limit has been reached")
        lap = Lap(len(self.laps) + 1, total - (self.laps[-1].total_ns if self.laps else 0), total)
        laps = self.laps + [lap]
        self._save("running", total, laps)
        self.laps = laps
        return lap

    def reset(self, confirmed=False):
        if self.state == "running":
            raise ValueError("Pause the stopwatch before resetting it")
        if self.state != "paused" or not confirmed:
            return False
        self._save("idle", 0, [])
        self.state, self.accumulated_ns, self.anchor, self.laps = "idle", 0, None, []
        return True

    def checkpoint(self):
        self._save(self.state, self.elapsed_ns(), self.laps)
