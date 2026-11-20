"""Selection-bound, drift-free tick planning; no I/O, speech or clock mutation."""
SECOND = 10**9


class TickPlan:
    def __init__(self):
        self.reset()

    def reset(self):
        self.key, self.anchor, self.last = None, 0, 0

    def poll(self, now, key, *, eligible, blocked=False):
        if not eligible:
            self.reset()
            return None
        if key != self.key:
            self.key, self.anchor, self.last = key, now, 0
            return None
        slot = max(0, (now - self.anchor) // SECOND)
        if slot <= self.last:
            return None
        self.last = slot  # Consume skipped slots, including while an alert owns audio.
        if blocked:
            return None
        return int((slot - 1) % 2)
