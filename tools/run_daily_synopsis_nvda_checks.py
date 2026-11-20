"""Run source integration in two synthetic NVDA profiles/private desktops.

Copies source without building an add-on. Uses only the stable manifest as
existing NVDA loader metadata. Never installs into the user's regular NVDA.
"""
import ctypes
from ctypes import wintypes
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from run_on_this_day_nvda_probe import private_process, personal_hashes, nvda_pids
from awqati.domain import default_settings, Location, StoredLocation, LocationKind, CalculationMethod
from awqati.infrastructure import JsonSettingsRepository


def run(runtime, label):
	output = ROOT / 'docs/daily_synopsis_task32' / label
	output.mkdir(parents=True, exist_ok=True)
	initial, owners = personal_hashes(), nvda_pids()
	user = ctypes.WinDLL('user32', use_last_error=True)
	user.CreateDesktopW.argtypes = [wintypes.LPCWSTR, ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p]
	user.CreateDesktopW.restype = wintypes.HANDLE
	user.CloseDesktop.argtypes = [wintypes.HANDLE]
	results = []
	for language in ('ar', 'en'):
		profile = Path(tempfile.mkdtemp(prefix='task3-live-task5-' + language + '-', dir=ROOT / 'development_baseline'))
		addon = profile / 'addons/awqati'
		shutil.copytree(ROOT / 'addon', addon, ignore=shutil.ignore_patterns('__pycache__'))
		with zipfile.ZipFile(ROOT / 'dist/awqati-7.0.0.nvda-addon') as archive:
			(addon / 'manifest.ini').write_bytes(archive.read('manifest.ini'))
		scratch = profile / 'scratchpad/globalPlugins'
		scratch.mkdir(parents=True)
		shutil.copyfile(ROOT / 'tools/daily_synopsis_nvda_probe.py', scratch / 'task5Acceptance.py')
		(profile / 'source-root.txt').write_text(str(ROOT), encoding='utf-8')
		(profile / 'nvda.ini').write_text(f'''[general]
    language = {language}
    showWelcomeDialogAtStartup = False
    saveConfigurationOnExit = False
    askToExit = False
[development]
    enableScratchpadDir = True
[keyboard]
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
''', encoding='utf-8')
		settings = default_settings()
		settings.location = StoredLocation(LocationKind.CUSTOM, Location('test-riyadh', 'Test Riyadh', 24.6877, 46.7219, 'Asia/Riyadh'))
		settings.prayer.calculation_method = CalculationMethod.MAKKAH
		settings.calendar.hijri_adjustment_days = 2
		settings.general.all_automatic_alerts_enabled = False
		JsonSettingsRepository(profile / 'awqati/settings.json').save(settings)
		(profile / 'awqati/world_clock_updates.json').write_text(json.dumps({'schemaVersion': 1, 'enabled': False,
			'lastSuccessfulCheck': None, 'lastDataUpdate': None, 'failures': 0, 'nextAttempt': 0, 'lastError': None}), encoding='utf-8')
		settings_hash = hashlib.sha256((profile / 'awqati/settings.json').read_bytes()).hexdigest()
		name = 'AwqatiTask3_' + profile.name.replace('-', '_')
		desktop = user.CreateDesktopW(name, None, None, 0, 0x01FF, None)
		if not desktop:
			raise ctypes.WinError(ctypes.get_last_error())
		try:
			code = private_process([runtime, '--config-path', str(profile),
				'--log-file', str(profile / 'nvda.log'), '--debug-logging', '--minimal', '--no-sr-flag'], 'winsta0\\' + name)
			path = profile / 'live-result.json'
			if not path.is_file():
				raise RuntimeError('No result: ' + str(profile))
			result = json.loads(path.read_text(encoding='utf-8'))
			shutil.copyfile(profile / 'nvda.log', output / f'nvda_{language}.log')
			result.update(processExitCode=code, profile=str(profile),
				syntheticSettingsUnchanged=settings_hash == hashlib.sha256((profile / 'awqati/settings.json').read_bytes()).hexdigest())
			result['errorHeadersInLog'] = [line for line in (profile / 'nvda.log').read_text(encoding='utf-8', errors='replace').splitlines() if line.startswith('ERROR -')]
			(output / f'nvda_{language}.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
			results.append(result)
			print(language, result['passed'], len(result['checks']), result.get('error', ''), flush=True)
		finally:
			user.CloseDesktop(desktop)
	state = dict(personalConfigurationUnchanged=initial == personal_hashes(), personalNVDAProcessPreserved=owners <= nvda_pids(), filesChecked=len(initial), activeDesktopNeverSwitched=True)
	(output / 'nvda_user_state.json').write_text(json.dumps(state, indent=2), encoding='utf-8')
	assert state['personalConfigurationUnchanged'] and state['personalNVDAProcessPreserved']
	assert all(r['passed'] and r['processExitCode'] == 0 and r['syntheticSettingsUnchanged'] and not r['errorHeadersInLog'] for r in results)


if __name__ == '__main__':
	for runtime, label in ((str(ROOT/'development_baseline/nvda-2026.1-portable/nvda_noUIAccess.exe'), '2026.1'), (r'C:\Program Files\NVDA\nvda_noUIAccess.exe', '2026.3.1')):
		run(runtime, label)
