import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADDON = ROOT / "addon"
if str(ADDON) not in sys.path:
	sys.path.insert(0, str(ADDON))

from globalPlugins.awqati.nvda_adapter.multipress import MultiPressDispatcher


class Timer:
	def __init__(self, callback):
		self.callback, self.cancelled = callback, False
	def cancel(self): self.cancelled = True
	def fire(self): self.callback()


class TimerFactory:
	def __init__(self): self.timers = []
	def __call__(self, delay, callback):
		timer = Timer(callback)
		self.timers.append(timer)
		return timer


class MultiPressTests(unittest.TestCase):
	def setUp(self):
		self.factory, self.calls = TimerFactory(), []
		self.dispatcher = MultiPressDispatcher(self.factory, 400)
		self.handlers = tuple(lambda n=n: self.calls.append(n) for n in (1, 2, 3))

	def test_single_waits_for_timeout(self):
		self.dispatcher.press("a", self.handlers)
		self.assertEqual([], self.calls)
		self.factory.timers[-1].fire()
		self.assertEqual([1], self.calls)

	def test_double_and_triple_dispatch_once(self):
		self.dispatcher.press("a", self.handlers)
		old = self.factory.timers[-1]
		self.dispatcher.press("a", self.handlers)
		self.factory.timers[-1].fire()
		old.fire()
		self.assertEqual([2], self.calls)
		self.dispatcher.press("a", self.handlers)
		self.dispatcher.press("a", self.handlers)
		self.dispatcher.press("a", self.handlers)
		self.assertEqual([2, 3], self.calls)

	def test_two_press_command(self):
		self.dispatcher.press("g", self.handlers[:2])
		self.dispatcher.press("g", self.handlers[:2])
		self.assertEqual([2], self.calls)

	def test_different_command_invalidates_old_callback(self):
		self.dispatcher.press("a", self.handlers)
		old = self.factory.timers[-1]
		self.dispatcher.press("b", self.handlers[:2])
		old.fire()
		self.factory.timers[-1].fire()
		self.assertEqual([1], self.calls)

	def test_close_invalidates_pending_callback_and_is_idempotent(self):
		self.dispatcher.press("a", self.handlers)
		old = self.factory.timers[-1]
		self.dispatcher.close()
		self.dispatcher.close()
		old.fire()
		self.dispatcher.press("a", self.handlers)
		self.assertEqual([], self.calls)


if __name__ == "__main__":
	unittest.main()
