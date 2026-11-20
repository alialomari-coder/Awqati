"""Run the standalone basic or advanced dialog with existing Python/wx, never install NVDA.

--language ar|en; --date YYYY-MM-DD optionally fixes the day for review.
--data-directory selects an explicit active table for this standalone harness.
The real integration will pass its existing active provider to the dialog.
"""
import argparse
from datetime import date
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]


def prepare_wx():
	if str(ROOT / "addon/globalPlugins") not in sys.path:
		sys.path.insert(0, str(ROOT / "addon/globalPlugins"))
	try:
		import wx
		return wx
	except ImportError:
		# Reuse the already prepared local runtime, without installing packages.
		runtime = ROOT / "development_baseline/time-tools/wx-runtime"
		if not any((runtime / name).is_file() for name in ("wx/__init__.py", "wx/__init__.pyc")):
			raise RuntimeError("Existing wx runtime is unavailable") from None
		global _dll_directory
		_dll_directory = os.add_dll_directory(r"C:\Program Files\NVDA")
		sys.path.insert(0, str(runtime))
		import wx
		return wx


def create_model_dependencies(fixed_date=None, data_directory=None):
	from awqati.application.historical_conversion import HistoricalConversionService
	from awqati.infrastructure.ummalqura_provider import UmmAlQuraProvider
	from awqati.infrastructure.system_time import SystemNowProvider
	from awqati.infrastructure.timezone_provider import BundledTimezoneProvider
	from awqati.nvda_adapter.calendar_converter_model import local_today
	from types import SimpleNamespace
	lunar = UmmAlQuraProvider(data_directory)
	clock, zones = SystemNowProvider(), BundledTimezoneProvider()
	location = SimpleNamespace(timezone_id="Asia/Riyadh")
	today = (lambda: date.fromisoformat(fixed_date)) if fixed_date else lambda: local_today(clock, zones, location)
	return HistoricalConversionService(lunar), lunar, today


def main():
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument("--language", choices=("ar", "en"), default="ar")
	parser.add_argument("--date")
	parser.add_argument("--advanced", action="store_true")
	parser.add_argument("--data-directory", type=Path)
	args = parser.parse_args()
	wx = prepare_wx()
	from awqati.nvda_adapter.calendar_converter_dialog import show_calendar_converter
	from awqati.nvda_adapter.calendar_converter_text import ConverterText
	if args.advanced:
		from awqati.nvda_adapter.advanced_converter_dialog import show_advanced_converter as show_calendar_converter
	app = wx.App(False)
	service, lunar, today = create_model_dependencies(args.date, args.data_directory)
	_ = ConverterText(args.language).gettext
	frame = wx.Frame(None, title="Awqati converter isolated launcher", size=(440, 140))
	panel = wx.Panel(frame)
	button = wx.Button(panel, label=_("Advanced conversion" if args.advanced else "Date converter"), pos=(20, 20))
	button.Bind(wx.EVT_BUTTON, lambda event: show_calendar_converter(frame,
		service, lunar, today, language=args.language))
	frame.Show()
	button.SetFocus()
	wx.CallAfter(lambda: show_calendar_converter(frame, service, lunar, today, language=args.language))
	app.MainLoop()


if __name__ == "__main__":
	main()
