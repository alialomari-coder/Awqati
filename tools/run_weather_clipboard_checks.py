"""Actual Windows clipboard acceptance in a separate private window station.

The user's interactive window station/clipboard is never opened or read.
Only the runner temporarily selects its new station to create its desktop;
it restores its original station before launching the dedicated wx child.
"""
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
OUTPUT=Path(os.environ.get('AWQATI_CLIPBOARD_OUTPUT', ROOT/'docs/weather_task2/clipboard.json'))


def api():
	user=ctypes.WinDLL('user32',use_last_error=True)
	user.GetProcessWindowStation.restype=wintypes.HANDLE
	user.SetProcessWindowStation.argtypes=[wintypes.HANDLE]
	user.CreateWindowStationW.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,ctypes.c_void_p]
	user.CreateWindowStationW.restype=wintypes.HANDLE
	user.CreateDesktopW.argtypes=[wintypes.LPCWSTR,ctypes.c_void_p,ctypes.c_void_p,wintypes.DWORD,wintypes.DWORD,ctypes.c_void_p]
	user.CreateDesktopW.restype=wintypes.HANDLE
	user.CloseDesktop.argtypes=[wintypes.HANDLE]
	user.CloseWindowStation.argtypes=[wintypes.HANDLE]
	user.GetUserObjectInformationW.argtypes=[wintypes.HANDLE,ctypes.c_int,ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(wintypes.DWORD)]
	return user


def worker(expected_station):
	user=api();buffer=ctypes.create_unicode_buffer(512);needed=wintypes.DWORD()
	if not user.GetUserObjectInformationW(user.GetProcessWindowStation(),2,buffer,ctypes.sizeof(buffer),ctypes.byref(needed)):
		raise ctypes.WinError(ctypes.get_last_error())
	# Refuse to touch ANY clipboard until exact station isolation is proven.
	assert buffer.value==expected_station and expected_station.lower()!='winsta0'
	from calendar_converter_launcher import prepare_wx
	wx=prepare_wx();app=wx.App(False)
	package_root = os.environ.get('AWQATI_PACKAGE_ROOT')
	if package_root:
		sys.path.insert(0, str(Path(package_root) / 'globalPlugins'))
	import builtins, types
	builtins._ = lambda text:text
	sys.modules['addonHandler']=types.SimpleNamespace(initTranslation=lambda:None)
	sys.modules['languageHandler']=types.SimpleNamespace(getLanguage=lambda:'en')
	# Import the exact weather dialog class; stub only NVDA's host modules.
	sys.modules['gui'] = types.SimpleNamespace()
	from awqati.nvda_adapter.weather_control import WeatherTextDialog
	from awqati.application.weather_formatters import WeatherFormatter
	from awqati.domain.weather import WeatherSettings
	from awqati.infrastructure.weather_provider import parse_weather
	from awqati.infrastructure import BundledTimezoneProvider
	sys.path.insert(0, str(ROOT/'tests'))
	from support.weather_fixtures import fixture
	from datetime import datetime, timezone
	now = datetime(2026,11,20,9,tzinfo=timezone.utc)
	zone = BundledTimezoneProvider().get_timezone('Asia/Riyadh')
	snapshot = parse_weather(fixture(now, zone), zone)
	settings = WeatherSettings(detail='detailed')
	results=[]
	for language in ('ar', 'en'):
		for report in ('current','today','future'):
			text=WeatherFormatter(settings,language,zone,now).format(snapshot,report,'Riyadh fixture',copyable=True)
			WeatherTextDialog.show(None,'Weather clipboard test',text)
			d=WeatherTextDialog._instance
			d.text.SetSelection(-1,-1)
			assert d.text.CanCopy()
			d.text.Copy()
			data=wx.TextDataObject();assert wx.TheClipboard.Open()
			try:assert wx.TheClipboard.GetData(data)
			finally:wx.TheClipboard.Close()
			assert data.GetText().replace('\r\n','\n')==text
			results.append(dict(language=language,report=report,characters=len(text),passed=True))
			d.Close();app.Yield()

	OUTPUT.write_text(json.dumps(dict(passed=True,station=buffer.value,
		userClipboardNeverOpened=True,checks=results),ensure_ascii=False,indent=2),encoding='utf-8')
	return 0


def main():
	if len(sys.argv)>1 and sys.argv[1]=='--worker':return worker(sys.argv[2])
	from run_on_this_day_nvda_probe import private_process
	user=api();original=user.GetProcessWindowStation()
	# Windows permits non-admin creation with a generated name only. Never use
	# an existing station: its clipboard may belong to another process.
	ctypes.set_last_error(0)
	station=user.CreateWindowStationW(None,0,0x37f,None)
	created_error=ctypes.get_last_error()
	if not station:raise ctypes.WinError(ctypes.get_last_error())
	desktop=None
	try:
		if created_error==183:raise RuntimeError('Station already exists; refusing clipboard access')
		buffer=ctypes.create_unicode_buffer(512);needed=wintypes.DWORD()
		if not user.GetUserObjectInformationW(station,2,buffer,ctypes.sizeof(buffer),ctypes.byref(needed)):
			raise ctypes.WinError(ctypes.get_last_error())
		name=buffer.value
		assert name.lower()!='winsta0'
		if not user.SetProcessWindowStation(station):raise ctypes.WinError(ctypes.get_last_error())
		try:
			desktop=user.CreateDesktopW('ClipboardTest',None,None,0,0x1ff,None)
			if not desktop:raise ctypes.WinError(ctypes.get_last_error())
		finally:
			if not user.SetProcessWindowStation(original):raise ctypes.WinError(ctypes.get_last_error())
		code=private_process([sys.executable,'-B',str(Path(__file__).resolve()),'--worker',name],name+'\\ClipboardTest')
		if code:raise RuntimeError('Private clipboard process failed: '+str(code))
		print(OUTPUT.read_text(encoding='utf-8'))
	finally:
		if desktop:user.CloseDesktop(desktop)
		user.CloseWindowStation(station)
	return 0


if __name__=='__main__':raise SystemExit(main())
