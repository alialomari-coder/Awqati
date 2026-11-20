"""Run preinstalled NVDA with new synthetic profiles on private desktops.

No add-on install, package extraction, desktop switch or personal profile writes.
Existing process-launch/isolation helpers are reused without modification.
"""
import ctypes
from ctypes import wintypes
import json
from pathlib import Path
import shutil
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from run_on_this_day_nvda_probe import private_process,personal_hashes,nvda_pids


def main():
	output=ROOT/'docs/historical_converter_task3'
	output.mkdir(parents=True,exist_ok=True)
	initial=personal_hashes();owner=nvda_pids()
	user=ctypes.WinDLL('user32',use_last_error=True)
	user.CreateDesktopW.argtypes=[wintypes.LPCWSTR,ctypes.c_void_p,ctypes.c_void_p,wintypes.DWORD,wintypes.DWORD,ctypes.c_void_p]
	user.CreateDesktopW.restype=wintypes.HANDLE
	user.CloseDesktop.argtypes=[wintypes.HANDLE]
	results=[]
	for language in ('ar','en'):
		profile=Path(tempfile.mkdtemp(prefix='task3-live-'+language+'-',dir=ROOT/'development_baseline'))
		scratch=profile/'scratchpad/globalPlugins';scratch.mkdir(parents=True)
		shutil.copyfile(ROOT/'tools/calendar_converter_nvda_probe.py',scratch/'task3Acceptance.py')
		(profile/'source-root.txt').write_text(str(ROOT),encoding='utf-8')
		(profile/'nvda.ini').write_text(f'''[general]
    language = {language}
    showWelcomeDialogAtStartup = False
    saveConfigurationOnExit = False
    askToExit = False
[development]
    enableScratchpadDir = True
[update]
    autoCheck = False
    startupNotification = False
[addonStore]
    automaticUpdates = disabled
[speech]
    synth = espeak
[braille]
    display = noBraille
''',encoding='utf-8')
		name='AwqatiTask3_'+profile.name.replace('-','_')
		desktop=user.CreateDesktopW(name,None,None,0,0x01FF,None)
		if not desktop:raise ctypes.WinError(ctypes.get_last_error())
		try:
			code=private_process([r'C:\Program Files\NVDA\nvda_noUIAccess.exe','--config-path',str(profile),
				'--log-file',str(profile/'nvda.log'),'--debug-logging','--minimal'],'winsta0\\'+name)
			path=profile/'live-result.json'
			if not path.is_file():raise RuntimeError('No live result: '+str(profile))
			result=json.loads(path.read_text(encoding='utf-8'));result['processExitCode']=code
			result['profile']=str(profile)
			result['errorHeadersInLog']=[line for line in (profile/'nvda.log').read_text(encoding='utf-8',errors='replace').splitlines()
				if line.startswith('ERROR -')]
			(output/f'nvda_{language}.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
			results.append(result)
			print(language,result['passed'],len(result['checks']),result.get('error',''),flush=True)
		finally:user.CloseDesktop(desktop)
	unchanged=initial==personal_hashes();preserved=owner<=nvda_pids()
	(output/'nvda_user_state.json').write_text(json.dumps(dict(personalConfigurationUnchanged=unchanged,
		personalNVDAProcessPreserved=preserved,filesChecked=len(initial),activeDesktopNeverSwitched=True),indent=2),encoding='utf-8')
	assert unchanged and preserved
	assert all(r['passed'] and r['processExitCode']==0 for r in results)


if __name__=='__main__':main()
