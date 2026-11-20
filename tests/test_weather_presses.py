"""Exercise the production settled-press state machine without importing NVDA."""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
tree = ast.parse((ROOT / "addon/globalPlugins/awqati/nvda_adapter/weather_control.py").read_text("utf-8"))
scope = {}
exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "WeatherPresses"], type_ignores=[]), "weather_presses", "exec"), scope)
WeatherPresses = scope["WeatherPresses"]


class Timer:
    def __init__(self, delay, callback, *args): self.delay, self.callback, self.args, self.stopped = delay, callback, args, False
    def Stop(self): self.stopped = True
    def fire(self): self.callback(*self.args)


class PressTests(unittest.TestCase):
    def test_only_final_report_for_one_two_three_presses_and_no_network_before_settle(self):
        for count, report in ((1, "current"), (2, "today"), (3, "future"), (4, "future")):
            timers, reports, cancellations = [], [], []
            def schedule(*args):
                timer = Timer(*args); timers.append(timer); return timer
            presses = WeatherPresses(schedule, lambda: 500, reports.append, lambda: cancellations.append(True))
            for _ in range(count): presses.press()
            self.assertFalse(reports)
            for timer in timers: timer.fire()  # even a queued obsolete callback must do nothing
            self.assertEqual(reports, [report])
            self.assertEqual(len(cancellations), count)
            self.assertEqual(timers[-1].delay, 550)

    def test_termination_invalidates_queued_callback(self):
        timers, reports = [], []
        def schedule(*args):
            timer = Timer(*args); timers.append(timer); return timer
        presses = WeatherPresses(schedule, lambda: 500, reports.append, lambda: None)
        presses.press(); presses.close(); timers[-1].fire()
        self.assertFalse(reports)
