"""Built-bundle fresh install / 7.1-to-8 upgrade and bilingual real NVDA gates.

Each NVDA instance uses its own desktop and synthetic profile. No desktop switch,
personal install, personal clipboard access or physical-input claim.
"""
import argparse
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
sys.path[:0] = [str(ROOT / 'tools'), str(ROOT / 'addon/globalPlugins')]
from run_on_this_day_nvda_probe import private_process, personal_hashes, nvda_pids
from awqati.domain import default_settings, Location, StoredLocation, LocationKind, CalculationMethod
from awqati.infrastructure import JsonSettingsRepository


def main():
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument('--runtime', default=r'C:\Program Files\NVDA\nvda_noUIAccess.exe')
	parser.add_argument('--label', default='2026.3.1')
	parser.add_argument('--language', choices=('ar', 'en'))
	parser.add_argument('--mode', choices=('fresh', 'upgrade'))
	args = parser.parse_args()
	output = ROOT / 'docs/weather_801/install' / args.label
	output.mkdir(parents=True, exist_ok=True)
	package = ROOT / 'dist/awqati-8.0.1.nvda-addon'
	with zipfile.ZipFile(package) as z:
		assert z.testzip() is None
		inventory = {n: hashlib.sha256(z.read(n)).hexdigest() for n in z.namelist()}
	initial, owners = personal_hashes(), nvda_pids()
	user = ctypes.WinDLL('user32', use_last_error=True)
	user.CreateDesktopW.argtypes = [wintypes.LPCWSTR, ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p]
	user.CreateDesktopW.restype = wintypes.HANDLE
	user.CloseDesktop.argtypes = [wintypes.HANDLE]
	results = []
	for language in ((args.language,) if args.language else ('ar', 'en')):
		for mode in ((args.mode,) if args.mode else ('fresh', 'upgrade')):
			profile = Path(tempfile.mkdtemp(prefix=f'task3-live-task5-release801-{args.label}-{language}-{mode}-', dir=ROOT / 'development_baseline'))
			scratch = profile / 'scratchpad/globalPlugins'
			scratch.mkdir(parents=True)
			(profile / 'source-root.txt').write_text(str(ROOT), 'utf-8')
			(profile / 'package-inventory.json').write_text(json.dumps(inventory), 'utf-8')
			(profile / 'package-root.txt').write_text(str(profile / 'addons/awqati'), 'utf-8')
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
''', 'utf-8')
			settings = default_settings()
			settings.location = StoredLocation(LocationKind.CUSTOM, Location('test-riyadh', 'Test Riyadh', 24.6877, 46.7219, 'Asia/Riyadh'))
			settings.prayer.calculation_method = CalculationMethod.MAKKAH
			settings.calendar.hijri_adjustment_days = 2
			settings.general.all_automatic_alerts_enabled = False
			JsonSettingsRepository(profile / 'awqati/settings.json').save(settings)
			(profile / 'awqati/world_clock_updates.json').write_text(json.dumps(dict(schemaVersion=1, enabled=False, lastSuccessfulCheck=None, lastDataUpdate=None, failures=0, nextAttempt=0, lastError=None)), 'utf-8')
			raw = json.loads((profile / 'awqati/settings.json').read_text('utf-8'))
			raw['weather']['current'].pop('apparent_temperature', None)
			(profile / 'awqati/settings.json').write_text(json.dumps(raw, ensure_ascii=False, indent=2), 'utf-8')
			shutil.copyfile(profile / 'awqati/settings.json', profile / 'original-settings.json')
			settings_before = hashlib.sha256((profile / 'awqati/settings.json').read_bytes()).hexdigest()
			if mode == 'upgrade':
				with zipfile.ZipFile(ROOT / 'dist/awqati-8.0.0.nvda-addon') as z:
					z.extractall(profile / 'addons/awqati')
			(profile / 'install-instruction.json').write_text(json.dumps(dict(oldVersion='8.0.0' if mode == 'upgrade' else None, package=str(package))), 'utf-8')
			name = 'AwqatiTask3_' + profile.name.replace('-', '_')
			desktop = user.CreateDesktopW(name, None, None, 0, 0x1ff, None)
			if not desktop:
				raise ctypes.WinError(ctypes.get_last_error())
			try:
				for phase, probe in (('install', 'release801_install_probe.py'), ('acceptance', 'release801_acceptance_probe.py')):
					shutil.copyfile(ROOT / 'tools' / probe, scratch / 'release801Probe.py')
					code = private_process([args.runtime, '--config-path', str(profile), '--log-file', str(profile / f'{phase}.log'), '--debug-logging', '--minimal', '--no-sr-flag'], 'winsta0\\' + name)
					path = profile / 'live-result.json'
					if not path.exists():
						raise RuntimeError('No result: ' + str(profile))
					result = json.loads(path.read_text('utf-8'))
					result.update(processExitCode=code, profile=str(profile), phase=phase, mode=mode, language=language, packageSha256=hashlib.sha256(package.read_bytes()).hexdigest(), syntheticSettingsUnchanged=settings_before == hashlib.sha256((profile / 'awqati/settings.json').read_bytes()).hexdigest())
					result['errorHeadersInLog'] = [line for line in (profile / f'{phase}.log').read_text('utf-8', errors='replace').splitlines() if line.startswith('ERROR -')]
					(output / f'{language}_{mode}_{phase}.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), 'utf-8')
					shutil.copyfile(profile / f'{phase}.log', output / f'{language}_{mode}_{phase}.log')
					results.append(result)
					print(args.label, language, mode, phase, result['passed'], len(result['checks']), result.get('error', ''), flush=True)
					assert result['passed'] and code == 0 and (phase != 'install' or result['syntheticSettingsUnchanged']) and not result['errorHeadersInLog'], result.get('error', result['errorHeadersInLog'])
					path.unlink()
			finally:
				user.CloseDesktop(desktop)
	state = dict(personalConfigurationUnchanged=initial == personal_hashes(), personalNVDAProcessPreserved=owners <= nvda_pids(), filesChecked=len(initial), activeDesktopNeverSwitched=True, packageSha256=hashlib.sha256(package.read_bytes()).hexdigest(), runs=len(results))
	(output / 'user_state.json').write_text(json.dumps(state, indent=2), 'utf-8')
	assert state['personalConfigurationUnchanged'] and state['personalNVDAProcessPreserved']


if __name__ == '__main__':
	main()
