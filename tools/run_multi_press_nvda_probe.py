"""Launch preinstalled NVDA on a private desktop with synthetic dev17 profiles.

Does not switch desktops, terminate the owner's NVDA or change personal data.
The scratchpad probe runs inside each test process and exits it normally.
"""
import ctypes
from ctypes import wintypes
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'addon/globalPlugins'))
from awqati.domain import default_settings, Location, StoredLocation, LocationKind, CalculationMethod
from awqati.infrastructure import JsonSettingsRepository

class StartupInfo(ctypes.Structure):
    _fields_=[('cb',wintypes.DWORD),('lpReserved',wintypes.LPWSTR),('lpDesktop',wintypes.LPWSTR),('lpTitle',wintypes.LPWSTR),
        *[(n,wintypes.DWORD) for n in ('dwX','dwY','dwXSize','dwYSize','dwXCountChars','dwYCountChars','dwFillAttribute','dwFlags')],
        ('wShowWindow',wintypes.WORD),('cbReserved2',wintypes.WORD),('lpReserved2',ctypes.POINTER(ctypes.c_byte)),
        ('hStdInput',wintypes.HANDLE),('hStdOutput',wintypes.HANDLE),('hStdError',wintypes.HANDLE)]

class ProcessInfo(ctypes.Structure):
    _fields_=[('hProcess',wintypes.HANDLE),('hThread',wintypes.HANDLE),('processId',wintypes.DWORD),('threadId',wintypes.DWORD)]

def private_process(argv,desktop):
    """Use native STARTUPINFOW.lpDesktop; subprocess.STARTUPINFO omits it."""
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.CreateProcessW.argtypes=[wintypes.LPCWSTR,wintypes.LPWSTR,ctypes.c_void_p,ctypes.c_void_p,wintypes.BOOL,
        wintypes.DWORD,ctypes.c_void_p,wintypes.LPCWSTR,ctypes.POINTER(StartupInfo),ctypes.POINTER(ProcessInfo)]
    kernel.CreateProcessW.restype=wintypes.BOOL
    kernel.WaitForSingleObject.argtypes=[wintypes.HANDLE,wintypes.DWORD];kernel.WaitForSingleObject.restype=wintypes.DWORD
    kernel.GetExitCodeProcess.argtypes=[wintypes.HANDLE,ctypes.POINTER(wintypes.DWORD)]
    kernel.TerminateProcess.argtypes=[wintypes.HANDLE,wintypes.UINT]
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    si=StartupInfo();si.cb=ctypes.sizeof(si);si.lpDesktop=desktop;si.dwFlags=1;si.wShowWindow=0
    pi=ProcessInfo();command=ctypes.create_unicode_buffer(subprocess.list2cmdline(argv))
    if not kernel.CreateProcessW(argv[0],command,None,None,False,0,None,str(ROOT),ctypes.byref(si),ctypes.byref(pi)):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        if kernel.WaitForSingleObject(pi.hProcess,50000)!=0:
            kernel.TerminateProcess(pi.hProcess,1);kernel.WaitForSingleObject(pi.hProcess,10000)
            raise RuntimeError('Dedicated test process timed out')
        code=wintypes.DWORD();kernel.GetExitCodeProcess(pi.hProcess,ctypes.byref(code));return code.value
    finally:kernel.CloseHandle(pi.hThread);kernel.CloseHandle(pi.hProcess)

def nvda_pids():
    text=subprocess.check_output(['powershell','-NoProfile','-Command',
        '(Get-Process -Name nvda,nvda_uiAccess,nvda_noUIAccess -ErrorAction SilentlyContinue).Id | ConvertTo-Json -Compress'],text=True).strip()
    value=json.loads(text) if text else []
    return set(value if isinstance(value,list) else [value])

def personal_hashes():
    root=Path.home()/'AppData/Roaming/nvda'
    paths=[root/'nvda.ini',root/'gestures.ini']
    if (root/'awqati').exists():paths+=list((root/'awqati').rglob('*.json'))
    return {str(p):hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None for p in paths}

def run():
    initial=personal_hashes()
    owner_pids=nvda_pids()
    package=ROOT/'dist/awqati-5.0.0-dev17.nvda-addon'
    desktop_api=ctypes.WinDLL('user32',use_last_error=True)
    desktop_api.CreateDesktopW.argtypes=[wintypes.LPCWSTR,ctypes.c_void_p,ctypes.c_void_p,wintypes.DWORD,wintypes.DWORD,ctypes.c_void_p]
    desktop_api.CreateDesktopW.restype=wintypes.HANDLE
    desktop_api.CloseDesktop.argtypes=[wintypes.HANDLE]
    results=[]
    for language in ('ar','en'):
        profile=Path(tempfile.mkdtemp(prefix='dev17-live-'+language+'-',dir=ROOT/'development_baseline'))
        addon=profile/'addons/awqati';addon.mkdir(parents=True)
        with zipfile.ZipFile(package) as z:z.extractall(addon)
        scratch=profile/'scratchpad/globalPlugins';scratch.mkdir(parents=True)
        shutil.copyfile(ROOT/'tools/multi_press_nvda_probe.py',scratch/'dev17Acceptance.py')
        (profile/'nvda.ini').write_text(f'''[general]
    language = {language}
    showWelcomeDialogAtStartup = False
    saveConfigurationOnExit = False
    askToExit = False
[development]
    enableScratchpadDir = True
[keyboard]
    NVDAModifierKeys = 7
[update]
    autoCheck = False
    startupNotification = False
[addonStore]
    automaticUpdates = disabled
[speech]
    synth = espeak
[braille]
    display = noBraille
''',encoding='utf8')
        settings=default_settings()
        settings.location=StoredLocation(LocationKind.CUSTOM,Location('test-riyadh','Test Riyadh',24.6877,46.7219,'Asia/Riyadh'))
        settings.prayer.calculation_method=CalculationMethod.MAKKAH
        settings.general.all_automatic_alerts_enabled=False
        JsonSettingsRepository(profile/'awqati/settings.json').save(settings)
        (profile/'awqati/world_clock_updates.json').write_text(json.dumps({'schemaVersion':1,'enabled':False,
            'lastSuccessfulCheck':None,'lastDataUpdate':None,'failures':0,'nextAttempt':0,'lastError':None}),encoding='utf8')
        name='AwqatiDev17_'+profile.name.replace('-','_')
        desktop=desktop_api.CreateDesktopW(name,None,None,0,0x01FF,None)
        if not desktop:raise ctypes.WinError(ctypes.get_last_error())
        try:
            # Verify isolation with a plain Python child before launching NVDA.
            stamp=profile/'desktop-preflight.json'
            preflight="import ctypes,json,pathlib;from ctypes import wintypes;u=ctypes.WinDLL('user32');u.GetThreadDesktop.argtypes=[wintypes.DWORD];u.GetThreadDesktop.restype=wintypes.HANDLE;k=ctypes.WinDLL('kernel32');h=u.GetThreadDesktop(k.GetCurrentThreadId());u.GetUserObjectInformationW.argtypes=[wintypes.HANDLE,ctypes.c_int,ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(wintypes.DWORD)];b=ctypes.create_unicode_buffer(512);n=wintypes.DWORD();assert u.GetUserObjectInformationW(h,2,b,1024,ctypes.byref(n));pathlib.Path("+repr(str(stamp))+").write_text(json.dumps({'desktop':b.value}))"
            desktop_path='winsta0\\'+name
            if private_process([sys.executable,'-c',preflight],desktop_path)!=0:raise RuntimeError('Desktop preflight process failed')
            if json.loads(stamp.read_text())['desktop']!=name:raise RuntimeError('Private desktop not honored; refusing to start NVDA')
            code=private_process([r'C:\Program Files\NVDA\nvda_noUIAccess.exe','--config-path',str(profile),
                '--log-file',str(profile/'nvda.log'),'--debug-logging','--minimal'],desktop_path)
            path=profile/'live-result.json'
            if not path.exists():raise RuntimeError('Probe did not produce result: '+str(profile))
            result=json.loads(path.read_text('utf8'));result['processExitCode']=code
            result['profile']=str(profile);result['packageSha256']=hashlib.sha256(package.read_bytes()).hexdigest()
            log=(profile/'nvda.log').read_text('utf8',errors='replace')
            result['errorHeadersInLog']=[line for line in log.splitlines() if line.startswith('ERROR -')]
            target=ROOT/f'docs/multi_press_dev17_live_{language}.json'
            target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
            results.append(result)
            print(language,'passed' if result['passed'] else 'FAILED',len(result['checks']),'checks',flush=True)
            if not result['passed']:print(result.get('error','unknown failure'),flush=True)
        finally:
            desktop_api.CloseDesktop(desktop)
    unchanged=initial==personal_hashes()
    owner_running=owner_pids <= nvda_pids()
    (ROOT/'docs/multi_press_dev17_user_state.json').write_text(json.dumps({'personalConfigurationUnchanged':unchanged,
        'filesChecked':len(initial),'activeDesktopNeverSwitched':True,'personalNVDAProcessPreserved':owner_running,
        'nativeDesktopPreflightVerified':True},indent=2)+'\n',encoding='utf8')
    if not unchanged:raise RuntimeError('Personal NVDA data hashes changed during test')
    if not owner_running:raise RuntimeError('Personal NVDA process was not preserved')
    if not all(r['passed'] and r['processExitCode']==0 for r in results):raise RuntimeError('Live integration failed')
    print('Both languages passed; personal configuration unchanged')

if __name__=='__main__':run()
