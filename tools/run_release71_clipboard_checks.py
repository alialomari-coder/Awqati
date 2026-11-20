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
import tempfile
import zipfile
import hashlib

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
OUTPUT=Path(os.environ.get('AWQATI_CLIPBOARD_OUTPUT', ROOT/'docs/release_7_1_0/clipboard.json'))


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
	from awqati.nvda_adapter.text_dialog import SelectableTextDialog
	from awqati.application import AstronomyService, DailyInfoService, ArabianCalendarService, ArabicDailyInfoFormatter, EnglishDailyInfoFormatter
	from awqati.infrastructure import BundledTimezoneProvider, BundledArabianCalendarRepository
	from awqati.domain import Location, Instant
	import awqati.nvda_adapter.text_dialog as loaded_dialog
	assert package_root and Path(loaded_dialog.__file__).resolve().is_relative_to(Path(package_root).resolve())
	from datetime import datetime, timezone
	clock=types.SimpleNamespace(now=lambda:Instant(datetime(2026,11,19,9,tzinfo=timezone.utc)))
	zones=BundledTimezoneProvider()
	service=DailyInfoService(AstronomyService(clock,zones),ArabianCalendarService(BundledArabianCalendarRepository(),clock,zones))
	results=[]
	for formatter in (ArabicDailyInfoFormatter(),EnglishDailyInfoFormatter()):
		for include in (False,True):
			text=formatter.format(service.read(Location('r','Riyadh',24.7136,46.6753,'Asia/Riyadh'),include_arabian_calendar=include))
			SelectableTextDialog.show(None,'Synopsis clipboard test',text)
			d=SelectableTextDialog._instance
			d.text.SetSelection(-1,-1)
			assert d.text.CanCopy()
			d.text.Copy()
			data=wx.TextDataObject();assert wx.TheClipboard.Open()
			try:assert wx.TheClipboard.GetData(data)
			finally:wx.TheClipboard.Close()
			assert data.GetText().replace('\r\n','\n')==text
			results.append(dict(language=formatter.language,heritage=include,characters=len(text),passed=True))
			d.Close();app.Yield()

	OUTPUT.write_text(json.dumps(dict(passed=True,station=buffer.value,
		userClipboardNeverOpened=True,checks=results),ensure_ascii=False,indent=2),encoding='utf-8')
	return 0


def main():
	if len(sys.argv)>1 and sys.argv[1]=='--worker':return worker(sys.argv[2])
	package=ROOT/'dist/awqati-7.1.0.nvda-addon'
	package_root=Path(tempfile.mkdtemp(prefix='release71-clipboard-',dir=ROOT/'development_baseline'))
	with zipfile.ZipFile(package) as archive:
		assert archive.testzip() is None
		archive.extractall(package_root)
		for name in archive.namelist():
			assert hashlib.sha256((package_root/name).read_bytes()).digest()==hashlib.sha256(archive.read(name)).digest()
	os.environ['AWQATI_PACKAGE_ROOT']=str(package_root)
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
		result=json.loads(OUTPUT.read_text('utf-8'))
		result.update(packageSha256=hashlib.sha256(package.read_bytes()).hexdigest(),packageRoot=str(package_root),moduleLoadedFromArtifact=True)
		OUTPUT.write_text(json.dumps(result,ensure_ascii=False,indent=2),'utf-8')
		print(OUTPUT.read_text(encoding='utf-8'))
	finally:
		if desktop:user.CloseDesktop(desktop)
		user.CloseWindowStation(station)
	return 0


if __name__=='__main__':raise SystemExit(main())
