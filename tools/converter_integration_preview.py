"""Optional keyboard review of the integration controller; no NVDA installation."""
from datetime import datetime, timezone
from types import SimpleNamespace as NS
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from calendar_converter_launcher import prepare_wx, create_model_dependencies


def main():
	wx = prepare_wx()
	from awqati.nvda_adapter.calendar_converter_control import CalendarConverterControl
	from awqati.infrastructure import BundledTimezoneProvider
	app = wx.App(False)
	frame = wx.Frame(None, title='Awqati task5 integration keyboard review', size=(520, 200))
	frame.prePopup = frame.postPopup = lambda: None
	panel = wx.Panel(frame)
	sizer = wx.BoxSizer(wx.VERTICAL)
	panel.SetSizer(sizer)
	_, lunar, _ = create_model_dependencies()
	settings = NS(runtime_settings=NS(location=NS(location=NS(timezone_id='Asia/Riyadh'))))
	clock = NS(now=lambda: NS(value=datetime.now(timezone.utc)))
	control = CalendarConverterControl(settings, clock, BundledTimezoneProvider(), lunar, lambda: 'ar', lambda text: None, frame)
	for advanced, label in ((False, 'فتح محوّل التاريخ'), (True, 'التحويل المتقدم')):
		button = wx.Button(panel, label=label)
		sizer.Add(button, 0, wx.ALL, 10)
		button.Bind(wx.EVT_BUTTON, lambda event, mode=advanced: control.show(mode, frame))
	frame.Bind(wx.EVT_CLOSE, lambda event: (control.close(), event.Skip()))
	frame.Show()
	panel.GetChildren()[0].SetFocus()
	app.MainLoop()


if __name__ == '__main__':
	main()
