"""Opt-in interactive acceptance on a private desktop, with independent return.

The main process stays on the normal desktop; a guardian owns the emergency
hotkey on the test desktop. Either process restores the original desktop if
the other exits. No installer, --replace, --quit, or personal setting writes.
"""
import argparse
import ctypes
from ctypes import wintypes as W
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import traceback

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'development_baseline/daily-synopsis-human32'
EVIDENCE=ROOT/'docs/daily_synopsis_task32/human_acceptance'
sys.path[:0]=[str(ROOT/'tools'),str(ROOT/'addon/globalPlugins')]
from run_on_this_day_nvda_probe import StartupInfo, ProcessInfo, personal_hashes, nvda_pids


def api():
    u=ctypes.WinDLL('user32',use_last_error=True)
    k=ctypes.WinDLL('kernel32',use_last_error=True)
    signatures={
        'CreateDesktopW':([W.LPCWSTR,ctypes.c_void_p,ctypes.c_void_p,W.DWORD,W.DWORD,ctypes.c_void_p],W.HANDLE),
        'OpenDesktopW':([W.LPCWSTR,W.DWORD,W.BOOL,W.DWORD],W.HANDLE),
        'OpenInputDesktop':([W.DWORD,W.BOOL,W.DWORD],W.HANDLE),
        'GetThreadDesktop':([W.DWORD],W.HANDLE),
        'SwitchDesktop':([W.HANDLE],W.BOOL),
        'CloseDesktop':([W.HANDLE],W.BOOL),
        'GetUserObjectInformationW':([W.HANDLE,ctypes.c_int,ctypes.c_void_p,W.DWORD,ctypes.POINTER(W.DWORD)],W.BOOL),
        'RegisterHotKey':([W.HWND,ctypes.c_int,W.UINT,W.UINT],W.BOOL),
        'UnregisterHotKey':([W.HWND,ctypes.c_int],W.BOOL),
        'PeekMessageW':([ctypes.POINTER(W.MSG),W.HWND,W.UINT,W.UINT,W.UINT],W.BOOL),
        'PostThreadMessageW':([W.DWORD,W.UINT,W.WPARAM,W.LPARAM],W.BOOL),
        'GetForegroundWindow':([],W.HWND),
        'SetForegroundWindow':([W.HWND],W.BOOL),
        'MessageBoxW':([W.HWND,W.LPCWSTR,W.LPCWSTR,W.UINT],ctypes.c_int),
    }
    for name,(args,ret) in signatures.items():
        getattr(u,name).argtypes=args;getattr(u,name).restype=ret
    kernel_signatures={
        'CreateProcessW':([W.LPCWSTR,W.LPWSTR,ctypes.c_void_p,ctypes.c_void_p,W.BOOL,W.DWORD,ctypes.c_void_p,W.LPCWSTR,ctypes.POINTER(StartupInfo),ctypes.POINTER(ProcessInfo)],W.BOOL),
        'OpenProcess':([W.DWORD,W.BOOL,W.DWORD],W.HANDLE),
        'WaitForSingleObject':([W.HANDLE,W.DWORD],W.DWORD),
        'TerminateProcess':([W.HANDLE,W.UINT],W.BOOL),
        'CloseHandle':([W.HANDLE],W.BOOL),
        'CreateMutexW':([ctypes.c_void_p,W.BOOL,W.LPCWSTR],W.HANDLE),
        'GetCurrentThreadId':([],W.DWORD),
    }
    for name,(args,ret) in kernel_signatures.items():
        getattr(k,name).argtypes=args;getattr(k,name).restype=ret
    return u,k


def object_name(u,handle):
    value=ctypes.create_unicode_buffer(512);needed=W.DWORD()
    if not u.GetUserObjectInformationW(handle,2,value,ctypes.sizeof(value),ctypes.byref(needed)):
        raise ctypes.WinError(ctypes.get_last_error())
    return value.value


def current_desktop(u):
    handle=u.OpenInputDesktop(0,False,1)
    if not handle:return None  # Locked/secure desktop: never bypass it.
    try:return object_name(u,handle)
    finally:u.CloseDesktop(handle)


def restore(u,original,test_name):
    active=current_desktop(u)
    if active is None:return False
    if active != test_name:return True  # Do not steal another desktop.
    return bool(u.SwitchDesktop(original))


def start(k,argv,desktop):
    si=StartupInfo();si.cb=ctypes.sizeof(si);si.lpDesktop='winsta0\\'+desktop
    si.dwFlags=1;si.wShowWindow=0
    process=ProcessInfo();command=ctypes.create_unicode_buffer(subprocess.list2cmdline(argv))
    if not k.CreateProcessW(argv[0],command,None,None,False,0,None,str(ROOT),ctypes.byref(si),ctypes.byref(process)):
        raise ctypes.WinError(ctypes.get_last_error())
    k.CloseHandle(process.hThread)
    return process


def write(path,data):
    temp=path.with_suffix(path.suffix+'.tmp')
    temp.write_text(json.dumps(data,ensure_ascii=False,indent=2),'utf-8')
    temp.replace(path)


def verified_manifest():
    manifest=json.loads((BASE/'manifest.json').read_text('utf-8'))
    actual={p.relative_to(BASE).as_posix() for p in (BASE/'addon').rglob('*') if p.is_file()}
    actual.add('human_host.py')
    if actual!=set(manifest['files']):
        raise RuntimeError('Prepared source inventory mismatch')
    for folder,key in ((BASE,'files'),(Path(manifest['runtime']),'runtimeFiles')):
        for relative,expected in manifest[key].items():
            path=(folder/relative).resolve()
            if not path.is_relative_to(folder.resolve()) or hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
                raise RuntimeError('Prepared file fingerprint mismatch: '+relative)
    return manifest


def prepare_profile(language,heritage,manifest=None):
    manifest=manifest if manifest is not None else verified_manifest()
    sessions=BASE/'sessions';sessions.mkdir(exist_ok=True)
    profile=Path(tempfile.mkdtemp(prefix='human32-',dir=sessions))
    shutil.copytree(BASE/'addon',profile/'addons/awqati')
    scratch=profile/'scratchpad/globalPlugins';scratch.mkdir(parents=True)
    shutil.copyfile(BASE/'human_host.py',scratch/'humanAcceptanceWorkspace.py')
    (profile/'nvda.ini').write_text(f'''[general]
    language = {language}
    showWelcomeDialogAtStartup = False
    saveConfigurationOnExit = False
    askToExit = False
[development]
    enableScratchpadDir = True
[keyboard]
    NVDAModifierKeys = 7
    multiPressTimeout = 500
[update]
    autoCheck = False
    startupNotification = False
[addonStore]
    automaticUpdates = disabled
[speech]
    synth = espeak
[braille]
    display = noBraille
''','utf-8')
    from awqati.domain import default_settings,Location,StoredLocation,LocationKind,CalculationMethod
    from awqati.infrastructure import JsonSettingsRepository
    settings=default_settings()
    settings.location=StoredLocation(LocationKind.CUSTOM,Location('human-fixture','Riyadh acceptance fixture',24.7136,46.6753,'Asia/Riyadh'))
    settings.prayer.calculation_method=CalculationMethod.MAKKAH
    settings.general.all_automatic_alerts_enabled=False
    settings.calendar.include_arabian_calendar_in_daily_info=heritage
    JsonSettingsRepository(profile/'awqati/settings.json').save(settings)
    write(profile/'awqati/world_clock_updates.json',dict(schemaVersion=1,enabled=False,lastSuccessfulCheck=None,lastDataUpdate=None,failures=0,nextAttempt=0,lastError=None))
    return profile,Path(manifest['runtime'])/'nvda_noUIAccess.exe'


def guardian(profile,parent_pid):
    u,k=api()
    options=json.loads((profile/'session.json').read_text('utf-8'))
    if not profile.resolve().is_relative_to((BASE/'sessions').resolve()) or not profile.name.startswith('human32-'):
        raise RuntimeError('Refusing a non-test profile')
    test_name=options['desktop']
    if object_name(u,u.GetThreadDesktop(k.GetCurrentThreadId())) != test_name:
        raise RuntimeError('Guardian must run on its own test desktop')
    original=u.OpenDesktopW(options['originalDesktop'],0,False,0x101)
    parent=k.OpenProcess(0x100000,False,parent_pid)
    if not original or not parent:raise ctypes.WinError(ctypes.get_last_error())
    # Ctrl+Alt+F10. F12 is reserved by Windows for debugger hotkeys.
    if not u.RegisterHotKey(None,0x3232,0x4003,0x79):
        raise ctypes.WinError(ctypes.get_last_error())
    child=None;reason='guardian failure';restored=False;forced=False
    try:
        child=start(k,[options['runtime'],'--config-path',str(profile),'--log-file',str(profile/'nvda.log'),
            '--log-level','20','--minimal','--no-sr-flag'],test_name)
        write(profile/'guardian-ready.json',dict(hotkeyRegistered=True,childPid=child.processId,guardianPid=os.getpid()))
        began=time.monotonic();injected=False
        while True:
            msg=W.MSG()
            if u.PeekMessageW(ctypes.byref(msg),None,0,0,1) and msg.message==0x312 and msg.wParam==0x3232:
                reason='preflight synthetic hotkey' if injected else 'return hotkey';break
            if k.WaitForSingleObject(parent,0)==0:reason='launcher exited';break
            if k.WaitForSingleObject(child.hProcess,0)==0:reason='test NVDA exited';break
            if (profile/'return.request').exists():reason='workspace return button';break
            if (profile/'guardian-stop.request').exists():reason='launcher return request';break
            if (profile/'host-error.txt').exists():reason='workspace startup error';break
            if not (profile/'host-ready.json').exists() and time.monotonic()-began>30:
                reason='startup timeout';break
            if options['preflight'] and (profile/'host-ready.json').exists() and not injected:
                injected=True
                if not u.PostThreadMessageW(k.GetCurrentThreadId(),0x312,0x3232,0):
                    raise ctypes.WinError(ctypes.get_last_error())
            if time.monotonic()-began>600:reason='ten minute safety timeout';break
            time.sleep(0.05)
    finally:
        # Restore first, so a nonresponsive test NVDA cannot leave the user mute.
        while not restore(u,original,test_name):time.sleep(0.2)
        restored=True
        (profile/'stop.request').touch()
        if child:
            if k.WaitForSingleObject(child.hProcess,12000)!=0:
                forced=True
                k.TerminateProcess(child.hProcess,1)  # Only our CreateProcess handle.
                k.WaitForSingleObject(child.hProcess,3000)
            k.CloseHandle(child.hProcess)
        write(profile/'guardian-result.json',dict(reason=reason,returnedOrAlreadyOutsideTestDesktop=restored,
            switchedForPreflight=False if options['preflight'] else None,forcedTestChildTermination=forced,humanAcceptance=None))
        u.UnregisterHotKey(None,0x3232)
        u.CloseDesktop(original);k.CloseHandle(parent)


def launch(language,heritage,preflight):
    u,k=api();EVIDENCE.mkdir(parents=True,exist_ok=True)
    mutex=k.CreateMutexW(None,False,'Local\\AwqatiHumanAcceptance32')
    if not mutex or ctypes.get_last_error()==183:
        if mutex:k.CloseHandle(mutex)
        raise RuntimeError('هناك جلسة قبول مفتوحة بالفعل. عد منها أولًا باستعمال Control Alt F10.')
    original=None;desktop=None;guard=None;profile=None;switched=False
    old_focus=u.GetForegroundWindow();before=personal_hashes();owners=nvda_pids()
    try:
        active=current_desktop(u)
        if active!='Default':raise RuntimeError('ابدأ الاختبار من سطح مكتب Windows المعتاد والمفتوح فقط.')
        original=u.OpenDesktopW(active,0,False,0x101)
        if not original:raise ctypes.WinError(ctypes.get_last_error())
        manifest=verified_manifest()
        if not preflight:
            runtime=Path(manifest['runtime'])/'nvda_noUIAccess.exe'
            if subprocess.run([str(runtime),'--check-running'],creationflags=0x08000000,timeout=8).returncode!=0:
                raise RuntimeError('لم يُكتشف NVDA معتاد على سطح المكتب الحالي. شغّله أولًا؛ لن نبدأ جلسة قد تعود منها دون قارئ شاشة.')
            explanation=('ستبدأ جلسة NVDA 2026.1 معزولة لمدة أقصاها عشر دقائق. '
                'سيبقى NVDA المعتاد مفتوحًا. العودة في أي وقت: Control Alt F10. '
                + ('الواجهة عربية، ' if language=='ar' else 'الواجهة إنجليزية، ')
                + ('والتراث مفعّل. ' if heritage else 'والتراث معطّل. ')
                + 'النسخ يستبدل حافظة Windows المشتركة. اضغط Enter للبدء أو Escape للإلغاء.')
            if u.MessageBoxW(None,explanation,'أوقاتي: بدء القبول البشري',0x10001)!=1:return
        profile,runtime=prepare_profile(language,heritage,manifest)
        name='AwqatiHuman32_'+profile.name.replace('-','_')
        desktop=u.CreateDesktopW(name,None,None,0,0x1ff,None)
        if not desktop:raise ctypes.WinError(ctypes.get_last_error())
        write(profile/'session.json',dict(desktop=name,originalDesktop=active,runtime=str(runtime),
            language=language,heritage=heritage,preflight=preflight,humanAcceptance=None))
        guard=start(k,[sys.executable,'-B',str(Path(__file__).resolve()),'--guardian',str(profile),'--parent',str(os.getpid())],name)
        deadline=time.monotonic()+35
        while not ((profile/'guardian-ready.json').exists() and (profile/'host-ready.json').exists()):
            if k.WaitForSingleObject(guard.hProcess,0)==0:raise RuntimeError('تعذر تجهيز مفتاح العودة أو تشغيل بيئة الاختبار. لم يُبدّل سطح المكتب.')
            if time.monotonic()>deadline:raise RuntimeError('انتهت مهلة التجهيز. لم يُبدّل سطح المكتب.')
            time.sleep(0.1)
        if not preflight:
            if current_desktop(u)!=active:raise RuntimeError('تغير سطح المكتب أثناء التجهيز؛ أُلغي الانتقال الآمن.')
            if not u.SwitchDesktop(desktop):raise ctypes.WinError(ctypes.get_last_error())
            switched=True
        while k.WaitForSingleObject(guard.hProcess,100)!=0:
            pass
        result_path=profile/'guardian-result.json'
        if not result_path.exists():raise RuntimeError('انتهت عملية الحماية دون إيصال؛ أُعيد سطح المكتب الأصلي.')
        result=json.loads(result_path.read_text('utf-8'))
        if preflight and result['reason']!='preflight synthetic hotkey':
            raise RuntimeError('Preflight failed: '+result['reason'])
        result.update(preflight=preflight,switchedToTestDesktop=switched,profile=str(profile),language=language,
            heritage=heritage,host=json.loads((profile/'host-ready.json').read_text('utf-8')),
            personalConfigurationUnchanged=before==personal_hashes(),personalProcessesPreserved=owners<=nvda_pids(),
            personalFilesChecked=len(before),errorHeadersInLog=[line for line in (profile/'nvda.log').read_text('utf-8',errors='replace').splitlines() if line.startswith('ERROR -')])
        write(EVIDENCE/('preflight_'+language+'.json' if preflight else 'last_session.json'),result)
        if not result['personalConfigurationUnchanged'] or not result['personalProcessesPreserved']:
            raise RuntimeError('لم تتطابق حالة NVDA المعتاد مع خط البداية. راجع سجل الجلسة قبل إعادة الاختبار.')
        if preflight:print(json.dumps(result,ensure_ascii=False,indent=2))
        else:u.MessageBoxW(None,'انتهت جلسة الاختبار وعُدت إلى NVDA المعتاد. لم يُسجّل قبول بشري تلقائيًا؛ أرسل ملاحظاتك في المحادثة.','أوقاتي: العودة إلى البيئة المعتادة',0x10040)
    finally:
        if original and profile:
            while not restore(u,original,'AwqatiHuman32_'+profile.name.replace('-','_')):time.sleep(0.2)
        if profile:(profile/'guardian-stop.request').touch()
        if guard:
            # The guardian owns graceful shutdown and fallback termination of
            # its test child; never terminate personal NVDA by process name.
            if k.WaitForSingleObject(guard.hProcess,20000)==0:k.CloseHandle(guard.hProcess)
        if desktop:u.CloseDesktop(desktop)
        if original:u.CloseDesktop(original)
        if old_focus and not preflight:u.SetForegroundWindow(old_focus)
        k.CloseHandle(mutex)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--language',choices=('ar','en'),default='ar')
    parser.add_argument('--heritage',choices=('on','off'),default='on')
    parser.add_argument('--preflight',action='store_true')
    parser.add_argument('--guardian',type=Path)
    parser.add_argument('--parent',type=int)
    args=parser.parse_args()
    try:
        if args.guardian:guardian(args.guardian,args.parent)
        else:launch(args.language,args.heritage=='on',args.preflight)
        return 0
    except Exception:
        detail=traceback.format_exc()
        if args.guardian:
            (args.guardian/'guardian-error.txt').write_text(detail,'utf-8')
        elif args.preflight:print(detail)
        else:
            EVIDENCE.mkdir(parents=True,exist_ok=True)
            (EVIDENCE/'launcher-error.txt').write_text(detail,'utf-8')
            api()[0].MessageBoxW(None,'تعذر بدء جلسة الاختبار أو إتمامها بأمان. بقيت بيئتك المعتادة دون استبدال.\n'+str(sys.exc_info()[1]),'أوقاتي: تعذر الاختبار المعزول',0x10010)
        return 1

if __name__=='__main__':raise SystemExit(main())
