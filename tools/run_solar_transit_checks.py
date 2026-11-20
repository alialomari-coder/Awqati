"""Run the standard gate with existing Python 3.13; restore frozen release ZIP.

The temporary interpreter follows run_release7_checks.py's existing approach
so wx binaries and child-process import tests use the correct runtime.
No packages are installed and no NVDA instance is modified.
"""
from pathlib import Path
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'docs/solar_transit_task11'


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    installation = ROOT / 'development_baseline/python-3.13.15'
    pth = installation / 'python313._pth'
    package = ROOT / 'dist/awqati-7.0.0.nvda-addon'
    original = package.read_bytes()
    summary = dict(stable_sha256=hashlib.sha256(original).hexdigest())
    with tempfile.TemporaryDirectory(prefix='awqati-solar-checks-') as directory:
        directory = Path(directory)
        shutil.copy2(installation / 'python.exe', directory / 'python.exe')
        for dll in installation.glob('*.dll'):
            shutil.copy2(dll, directory / dll.name)
        paths = [str((installation / line).resolve()) for line in pth.read_text().splitlines()
            if line.strip() and not line.startswith(('#', 'import '))]
        paths += [str(ROOT), str(ROOT / 'tests'), str(ROOT / 'addon/globalPlugins')]
        (directory / pth.name).write_text('\n'.join(paths) + '\n', encoding='utf-8')
        try:
            with (OUTPUT / 'checks.log').open('w', encoding='utf-8') as stream:
                result = subprocess.run([str(directory / 'python.exe'), '-B', 'tools/run_checks.py'],
                    cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT)
            summary['exit_code'] = result.returncode
            if package.exists():
                summary['test_build_sha256'] = hashlib.sha256(package.read_bytes()).hexdigest()
        finally:
            package.write_bytes(original)
            summary['restored_stable'] = hashlib.sha256(package.read_bytes()).hexdigest() == summary['stable_sha256']
            (OUTPUT / 'build_verification.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    log = (OUTPUT / 'checks.log').read_text(encoding='utf-8')
    count = re.search(r'Ran (\d+) tests', log)
    summary['tests'] = int(count[1]) if count else None
    summary['successful'] = result.returncode == 0
    summary['python'] = '3.13.15'
    (OUTPUT / 'test_summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(json.dumps(summary, indent=2))
    return result.returncode


if __name__ == '__main__':
    raise SystemExit(main())
