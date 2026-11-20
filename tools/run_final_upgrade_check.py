"""Exercise 4.0.0 -> current settings with the byte-verified published package.

Uses synthetic data in a temporary directory, never a personal NVDA profile.
This checks persistence compatibility, not NVDA's interactive package installer.
"""
from pathlib import Path
import hashlib
import json
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
STABLE_SHA256 = "938c99ea08346c94d944325eaa5646144041e6abcfcea4d3cf85a8122abb1baa"


def main():
    stable = ROOT / "development_baseline/awqati-4.0.0.nvda-addon"
    if hashlib.sha256(stable.read_bytes()).hexdigest() != STABLE_SHA256:
        raise RuntimeError("Published 4.0.0 package checksum mismatch")
    with tempfile.TemporaryDirectory(prefix="awqati-upgrade-") as folder:
        work = Path(folder)
        with zipfile.ZipFile(stable) as archive:
            archive.extractall(work / "stable")
        settings = work / "settings.json"
        create = '''
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from awqati.domain import default_settings, Location, StoredLocation, LocationKind, CalculationMethod, PrayerEventName
from awqati.infrastructure import JsonSettingsRepository
s=default_settings()
s.location=StoredLocation(LocationKind.CUSTOM,Location('upgrade-test','اختبار الترقية',24.6877,46.7219,'Asia/Riyadh'))
s.prayer.calculation_method=CalculationMethod.MAKKAH
s.prayer.corrections_minutes[PrayerEventName.FAJR]=3
s.general.all_automatic_alerts_enabled=False
s.adhkar.daily_wird.text='نص محفوظ من الإصدار المستقر — preserved reminder'
JsonSettingsRepository(Path(sys.argv[2])).save(s)
'''
        subprocess.run([sys.executable, "-c", create, str(work / "stable/globalPlugins"), str(settings)], check=True)
        before = settings.read_bytes()
        read_save = '''
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from awqati.infrastructure import JsonSettingsRepository
p=Path(sys.argv[2]); r=JsonSettingsRepository(p)
before=p.read_bytes(); s=r.load()
assert p.read_bytes()==before, 'Loading rewrote old settings'
assert s.location.location.name=='اختبار الترقية'
assert s.adhkar.daily_wird.text=='نص محفوظ من الإصدار المستقر — preserved reminder'
r.save(s)
'''
        subprocess.run([sys.executable, "-c", read_save, str(ROOT / "addon/globalPlugins"), str(settings)], check=True)
        # Compare every serialized setting, including nested values, not just samples.
        if json.loads(before) != json.loads(settings.read_bytes()):
            raise AssertionError("Upgrade lost or changed a persisted setting")
        subprocess.run([sys.executable, "-c", read_save, str(work / "stable/globalPlugins"), str(settings)], check=True)
        result = {"passed": True, "stablePackageSha256": STABLE_SHA256,
                  "syntheticDataOnly": True, "loadDoesNotWrite": True,
                  "allPersistedSettingsPreserved": True, "stableCanReadSavedSettings": True,
                  "scope": "Actual 4.0 serializer -> current load/save -> actual 4.0 reader. Not an installer or live NVDA upgrade test."}
        (ROOT / "docs/final_5_upgrade.json").write_text(json.dumps(result, indent=2) + "\n", "utf8")
        print("PASS: actual 4.0.0 settings preserved through current load/save and stable re-read")


if __name__ == "__main__":
    main()
