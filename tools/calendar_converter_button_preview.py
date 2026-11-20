"""Visible, deterministic native-message review fixture; no add-on integration.

Starts a real result/error from a preset date so manual input timing and UIA
set-value support do not affect the limited button-label review.
"""
import argparse
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from calendar_converter_launcher import prepare_wx,create_model_dependencies


def main():
	parser=argparse.ArgumentParser(description=__doc__)
	parser.add_argument('--language',choices=('ar','en'),required=True)
	parser.add_argument('--kind',choices=('result','error'),required=True)
	args=parser.parse_args()
	wx=prepare_wx()
	from awqati.nvda_adapter.calendar_converter_dialog import CalendarConverterDialog
	app=wx.App(False)
	dependencies=create_model_dependencies('2026-09-12')
	frame=wx.Frame(None,title=f'Awqati button label review {args.language} {args.kind}',size=(460,140))
	button=wx.Button(frame,label='Open review fixture')
	def open_fixture(event=None):
		dialog=CalendarConverterDialog(frame,*dependencies,language=args.language)
		if args.kind=='error':dialog.entries['year'].ChangeValue('365')
		wx.CallLater(200,dialog._convert)
		try:dialog.ShowModal()
		finally:dialog.Destroy();button.SetFocus()
	button.Bind(wx.EVT_BUTTON,open_fixture)
	frame.Show();button.SetFocus()
	wx.CallAfter(open_fixture)
	app.MainLoop()


if __name__=='__main__':main()
