"""Official stable install, upgrade and bilingual smoke on private desktops.

Never switches the active desktop, replaces personal add-ons or stops personal NVDA.
"""
from pathlib import Path
import ctypes
from ctypes import wintypes
import hashlib
import json
import shutil
import sys
import tempfile

from run_countdown_dev18_nvda_probe import private_process, nvda_pids, personal_hashes, ROOT
from awqati.domain import default_settings, Location, StoredLocation, LocationKind, CalculationMethod
from awqati.infrastructure import JsonSettingsRepository


def main():
    sys.path.insert(0, str(ROOT))
    from buildVars import addon_info
    version = addon_info['addon_version']
    package = ROOT / f'dist/awqati-{version}.nvda-addon'
    # Keep the tested artifact independent of SCons' clean/build lifecycle.
    retained = Path(tempfile.mkdtemp(prefix='final5-package-', dir=ROOT/'development_baseline')) / package.name
    shutil.copyfile(package, retained)
    package = retained
    stable = ROOT / 'development_baseline/awqati-4.0.0.nvda-addon'
    if hashlib.sha256(stable.read_bytes()).hexdigest() != '938c99ea08346c94d944325eaa5646144041e6abcfcea4d3cf85a8122abb1baa':
        raise RuntimeError('Stable archive checksum mismatch')
    hashes, pids = personal_hashes(), nvda_pids()
    api = ctypes.WinDLL('user32', use_last_error=True)
    api.CreateDesktopW.argtypes = [wintypes.LPCWSTR, ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p]
    api.CreateDesktopW.restype = wintypes.HANDLE
    api.CloseDesktop.argtypes = [wintypes.HANDLE]
    all_results = []
    for lang in ('ar', 'en'):
        profile = Path(tempfile.mkdtemp(prefix=f'final5-live-{lang}-', dir=ROOT/'development_baseline'))
        scratch = profile/'scratchpad/globalPlugins'
        scratch.mkdir(parents=True)
        shutil.copyfile(ROOT/'tools/final_nvda_review_probe.py', scratch/'finalReview.py')
        (profile/'nvda.ini').write_text(f'''[general]
    language = {lang}
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
''', 'utf8')
        settings = default_settings()
        settings.location = StoredLocation(LocationKind.CUSTOM, Location('test-riyadh','Test Riyadh',24.6877,46.7219,'Asia/Riyadh'))
        settings.prayer.calculation_method = CalculationMethod.MAKKAH
        settings.general.all_automatic_alerts_enabled = False
        JsonSettingsRepository(profile/'awqati/settings.json').save(settings)
        (profile/'awqati/sentinel.txt').write_text('preserve synthetic user file','utf8')
        (profile/'awqati/world_clock_updates.json').write_text(json.dumps({'schemaVersion':1,'enabled':False,
            'lastSuccessfulCheck':None,'lastDataUpdate':None,'failures':0,'nextAttempt':0,'lastError':None}), 'utf8')
        name = 'AwqatiFinal5_'+profile.name.replace('-','_')
        desktop = api.CreateDesktopW(name,None,None,0,0x01FF,None)
        if not desktop:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            for phase in ('install4', 'upgrade', 'current', 'custom-auto'):
                if phase == 'custom-auto':
                    repository = JsonSettingsRepository(profile/'awqati/settings.json')
                    affected = repository.load()
                    affected.prayer.calculation_method = CalculationMethod.AUTO
                    repository.save(affected)
                    (profile/'settings-before-choice.json').write_bytes((profile/'awqati/settings.json').read_bytes())
                (profile/'review-command.json').write_text(json.dumps({'phase':phase,'version':version,
                    'package':str(stable if phase=='install4' else package)}),'utf8')
                code = private_process([r'C:\Program Files\NVDA\nvda_noUIAccess.exe','--config-path',str(profile),
                    '--log-file',str(profile/f'nvda-{phase}.log'),'--debug-logging','--minimal'], 'winsta0\\'+name)
                result = json.loads((profile/f'review-{phase}.json').read_text('utf8'))
                result.update(processExitCode=code, profile=str(profile), packageSha256=hashlib.sha256(package.read_bytes()).hexdigest())
                log = (profile/f'nvda-{phase}.log').read_text('utf8', errors='replace')
                result['errorHeadersInLog'] = [line for line in log.splitlines() if line.startswith('ERROR -')]
                (ROOT/f'docs/final_5_nvda_{lang}_{phase}.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf8')
                all_results.append(result)
                print(lang,phase,'PASS' if result['passed'] else result.get('error'),flush=True)
                if not result['passed'] or code:
                    raise RuntimeError('NVDA isolated review failed')
        finally:
            api.CloseDesktop(desktop)
    state = {'personalConfigurationUnchanged': hashes == personal_hashes(), 'personalNVDAProcessesPreserved': pids <= nvda_pids(),
             'filesChecked':len(hashes), 'activeDesktopNeverSwitched':True}
    (ROOT/'docs/final_5_user_state.json').write_text(json.dumps(state,indent=2)+'\n','utf8')
    if not state['personalConfigurationUnchanged'] or not state['personalNVDAProcessesPreserved']:
        raise RuntimeError('Personal state changed during test')
    print('PASS: bilingual official install/upgrade/runtime smoke; personal configuration unchanged')


if __name__ == '__main__':
    main()
