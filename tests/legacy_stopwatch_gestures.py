# Historical dev16 fixture; never packaged or imported by production.
"""Defer selection using NVDA's repeat counter and configured timeout only.

No independent press counter or custom repeat interval. One pending action is
replaced by the next stopwatch sequence, and never survives plugin termination.
"""
from awqati.nvda_adapter import compat


class StopwatchGestures:
    def __init__(self, schedule=compat.schedule, repeat=compat.script_repeat_count, timeout=None):
        self.schedule, self.repeat = schedule, repeat
        self.timeout = timeout or self.native_timeout
        self.pending = None
        self.generation = 0
        self.closed = False

    @staticmethod
    def native_timeout():
        import config
        return config.conf["keyboard"]["multiPressTimeout"]

    def cancel(self):
        self.generation += 1
        if self.pending:
            self.pending.cancel()
            self.pending = None

    def submit(self, handlers):
        self.cancel()
        if self.closed:
            return
        count = self.repeat()
        # An accidental fourth or later press must never repeat reset or toggle.
        if count >= len(handlers):
            return
        generation = self.generation
        action = handlers[count]

        def execute():
            if self.closed or generation != self.generation:
                return
            self.pending = None
            self.generation += 1  # Consume this action even if a callback is queued twice.
            action()  # The stopwatch captures time here, before audio/speech.

        self.pending = self.schedule(self.timeout(), execute)

    def close(self):
        self.closed = True
        self.cancel()
