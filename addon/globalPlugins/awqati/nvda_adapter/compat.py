"""Feature-detected NVDA/wx compatibility used by the NVDA adapter."""

from __future__ import annotations

from typing import Callable


class _CallLaterHandle:
	def __init__(self, timer) -> None:
		self._timer = timer

	def cancel(self) -> None:
		if self._timer is not None:
			try:
				self._timer.Stop()
			finally:
				self._timer = None


def schedule(delay_ms: int, callback: Callable[[], None]):
	import wx
	return _CallLaterHandle(wx.CallLater(max(1, int(delay_ms)), callback))


def call_after(callback, *args) -> None:
	import wx
	wx.CallAfter(callback, *args)


def script_repeat_count() -> int:
	"""Return NVDA's official zero-based repeat count for the running script."""
	import scriptHandler
	getter = getattr(scriptHandler, "getLastScriptRepeatCount", None)
	if getter is None:
		return 0
	try:
		return max(0, int(getter()))
	except (TypeError, ValueError):
		return 0


def dispatch_repeated_script(handlers) -> None:
	"""Run the selected handler synchronously; the first press never waits."""
	handlers = tuple(handlers)
	if not handlers:
		raise ValueError("at least one repeated-script handler is required")
	handlers[min(script_repeat_count(), len(handlers) - 1)]()


def open_awqati_settings(panel_class) -> None:
	"""Target Awqati directly on NVDA versions exposing the category API."""
	import gui
	from gui.settingsDialogs import NVDASettingsDialog
	frame = gui.mainFrame
	if hasattr(frame, "_popupSettingsDialog"):
		frame._popupSettingsDialog(NVDASettingsDialog, panel_class)
		return
	if hasattr(frame, "popupSettingsDialog"):
		try:
			frame.popupSettingsDialog(NVDASettingsDialog, panel_class)
		except TypeError:
			frame.popupSettingsDialog(NVDASettingsDialog)
		return
	frame.onNVDASettingsCommand(None)


class SystemEventMonitor:
	"""Bind native wx power/time notifications when the running wx exposes them."""

	def __init__(self, window, on_resume, on_time_change) -> None:
		import wx
		self._window, self._bindings = window, []
		for name, callback in (("EVT_POWER_RESUME", on_resume), ("EVT_TIME_CHANGED", on_time_change)):
			event = getattr(wx, name, None)
			if event is not None:
				window.Bind(event, callback)
				self._bindings.append((event, callback))

	def close(self) -> None:
		for event, callback in self._bindings:
			try:
				self._window.Unbind(event, handler=callback)
			except Exception:
				pass
		self._bindings.clear()
