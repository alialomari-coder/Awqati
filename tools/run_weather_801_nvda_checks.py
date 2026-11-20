"""Source-only bilingual NVDA weather checks on private desktops and synthetic profiles."""
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
sys.path.insert(0, str(ROOT / "tools"))
from run_on_this_day_nvda_probe import private_process, personal_hashes, nvda_pids
from awqati.domain import default_settings, Location, StoredLocation, LocationKind, CalculationMethod
from awqati.infrastructure import JsonSettingsRepository


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", default=r"C:\Program Files\NVDA\nvda_noUIAccess.exe")
    parser.add_argument("--label", default="2026.3.1")
    parser.add_argument("--package", default="dist/awqati-8.0.1.nvda-addon")
    parser.add_argument("--output", default="docs/weather_801")
    parser.add_argument("--probe", default="tools/weather_801_nvda_probe.py")
    args = parser.parse_args()
    output = ROOT / args.output / args.label
    output.mkdir(parents=True, exist_ok=True)
    if not Path(args.runtime).is_file(): raise RuntimeError("NVDA runtime is unavailable: " + args.runtime)
    initial, owners = personal_hashes(), nvda_pids()
    stable_before = hashlib.sha256((ROOT / "dist/awqati-8.0.0.nvda-addon").read_bytes()).hexdigest()
    user = ctypes.WinDLL("user32", use_last_error=True)
    user.CreateDesktopW.argtypes = [wintypes.LPCWSTR, ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p]
    user.CreateDesktopW.restype = wintypes.HANDLE
    user.CloseDesktop.argtypes = [wintypes.HANDLE]
    results = []
    for language in ("ar", "en"):
        profile = Path(tempfile.mkdtemp(prefix="task3-live-task5-weather-" + language + "-", dir=ROOT / "development_baseline"))
        addon = profile / "addons/awqati"
        with zipfile.ZipFile(ROOT / args.package) as archive:
            assert archive.testzip() is None
            archive.extractall(addon)
        scratch = profile / "scratchpad/globalPlugins"
        scratch.mkdir(parents=True)
        shutil.copyfile(ROOT / args.probe, scratch / "weatherProbe.py")
        (profile / "source-root.txt").write_text(str(ROOT), "utf-8")
        (profile / "nvda.ini").write_text(f'''[general]
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
''', "utf-8")
        settings = default_settings()
        settings.location = StoredLocation(LocationKind.CUSTOM, Location("test", "Test Riyadh", 24.7, 46.7, "Asia/Riyadh"))
        settings.prayer.calculation_method = CalculationMethod.MAKKAH
        settings.general.all_automatic_alerts_enabled = False
        JsonSettingsRepository(profile / "awqati/settings.json").save(settings)
        (profile / "awqati/world_clock_updates.json").write_text(json.dumps(dict(schemaVersion=1, enabled=False, lastSuccessfulCheck=None, lastDataUpdate=None, failures=0, nextAttempt=0, lastError=None)), "utf-8")
        name = "AwqatiTask3_" + profile.name.replace("-", "_")
        desktop = user.CreateDesktopW(name, None, None, 0, 0x1ff, None)
        if not desktop: raise ctypes.WinError(ctypes.get_last_error())
        try:
            code = private_process([args.runtime, "--config-path", str(profile), "--log-file", str(profile / "nvda.log"), "--debug-logging", "--minimal", "--no-sr-flag"], "winsta0\\" + name)
            path = profile / "live-result.json"
            if not path.exists(): raise RuntimeError("No probe result; see " + str(profile / "nvda.log"))
            result = json.loads(path.read_text("utf-8"))
            result.update(exitCode=code, profile=str(profile), packageSha256=hashlib.sha256((ROOT / args.package).read_bytes()).hexdigest())
            result["errorsInLog"] = [line for line in (profile / "nvda.log").read_text("utf-8", errors="replace").splitlines() if line.startswith("ERROR -")]
            (output / f"{language}.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), "utf-8")
            shutil.copyfile(profile / "nvda.log", output / f"{language}.log")
            results.append(result)
            print(args.label, language, result["passed"], len(result["checks"]), result.get("error", ""), flush=True)
        finally: user.CloseDesktop(desktop)
    state = dict(personalConfigurationUnchanged=initial == personal_hashes(), personalProcessesPreserved=owners <= nvda_pids(), activeDesktopNeverSwitched=True, stablePackageUnchanged=stable_before == hashlib.sha256((ROOT / "dist/awqati-8.0.0.nvda-addon").read_bytes()).hexdigest())
    (output / "user_state.json").write_text(json.dumps(state, indent=2), "utf-8")
    assert all(state.values())
    assert all(r["passed"] and r["exitCode"] == 0 and not r["errorsInLog"] for r in results)

if __name__ == "__main__": main()
