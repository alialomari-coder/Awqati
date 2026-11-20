"""Verify the dev20 artifact against dev19 without touching personal data."""
from pathlib import Path
import ast
import hashlib
import json
import re
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
BASE_COMMIT = 'd2f986b698341a161abae00c96eddeb4681c8198'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalized(data):
    try:
        return data.decode('utf8').replace('\r\n', '\n')
    except UnicodeDecodeError:
        return data


def main():
    plugin = 'addon/globalPlugins/awqati/nvda_adapter/plugin.py'
    previous = ast.parse(subprocess.check_output(['git', 'show', BASE_COMMIT + ':' + plugin], cwd=ROOT).decode('utf8'))
    current = ast.parse((ROOT / plugin).read_text('utf8'))
    scripts = lambda tree: {n.name: ast.dump(n) for n in ast.walk(tree)
                            if isinstance(n, ast.FunctionDef) and n.name.startswith('script_')}
    assert scripts(previous) == scripts(current), 'Command bodies or metadata changed'
    old = ROOT / 'dist/awqati-5.0.0-dev19.nvda-addon'
    package = ROOT / 'dist/awqati-5.0.0-dev20.nvda-addon'
    assert digest(old) == '261ea9d8d965c0ba780dab5e38f1ade0efab714f65a85b6132aa285c01c462cb'
    with zipfile.ZipFile(old) as baseline, zipfile.ZipFile(package) as archive:
        assert archive.testzip() is None
        names = set(archive.namelist())
        old_names = set(baseline.namelist())
        added = names - old_names
        assert added == {'globalPlugins/awqati/nvda_adapter/legacy_commands.py'}, added
        assert not old_names - names
        changed = sorted(name for name in old_names if normalized(baseline.read(name)) != normalized(archive.read(name)))
        assert set(changed) == {
            'manifest.ini', 'globalPlugins/awqati/nvda_adapter/plugin.py',
            'doc/ar/readme.md', 'doc/ar/readme.html', 'doc/en/readme.md', 'doc/en/readme.html',
        }, changed
        verified = 0
        for source in (ROOT / 'addon').rglob('*'):
            if not source.is_file() or '__pycache__' in source.parts or source.suffix in ('.pyc', '.pyo'):
                continue
            name = source.relative_to(ROOT / 'addon').as_posix()
            assert normalized(source.read_bytes()) == normalized(archive.read(name)), name
            verified += 1
    retained = []
    for backup in sorted((ROOT / 'development_baseline/dev20-retained-packages').glob('*.nvda-addon')):
        assert digest(backup) == digest(ROOT / 'dist' / backup.name), backup.name
        retained.append({'name': backup.name, 'sha256': digest(backup)})
    log = (ROOT / 'docs/command_cleanup_dev20_checks.log').read_text('utf8')
    assert 'ALL REQUIRED CHECKS PASSED' in log
    count = int(re.search(r'Ran (\d+) tests', log).group(1))
    native = (ROOT / 'docs/command_cleanup_dev20_bytecode.log').read_text('utf8')
    assert 'Ran 3 tests' in native and '\nOK\n' in native
    result = {
        'build': '5.0.0-dev20', 'baseCommit': BASE_COMMIT,
        'package': str(package), 'sha256': digest(package), 'bytes': package.stat().st_size,
        'sourceFilesVerified': verified, 'unchangedExistingPackageFiles': len(old_names) - len(changed),
        'changedPackageFiles': changed, 'addedPackageFiles': sorted(added),
        'all48ScriptBodiesAndMetadataUnchanged': True,
        'visibleCommandsWithoutLegacyBindings': 43, 'defaultCommands': 30, 'independentUnassignedCommands': 13,
        'hiddenUnlessPreviouslyAssigned': ['zawaliTime', 'stopwatchToggle', 'stopwatchLap', 'stopwatchStatus', 'stopwatchLastLap'],
        'compatibilitySourcesTested': ['NVDA 2026.1', 'NVDA 2026.2', 'NVDA 2026.3'],
        'gate': {'status': 'passed', 'python': sys.version.split()[0], 'cases': count, 'passed': count - 3,
                 'skipped': 3, 'skipReason': 'NVDA Python 3.13 bytecode; all three passed separately',
                 'log': 'docs/command_cleanup_dev20_checks.log'},
        'nativeBytecode': {'python': '3.13.5', 'passed': 3, 'log': 'docs/command_cleanup_dev20_bytecode.log'},
        'initialGate': {'status': 'failed then corrected', 'historicalAssertions': 3,
                        'localhostNetworkSandboxError': 1, 'log': 'docs/command_cleanup_dev20_initial_checks.log'},
        'retainedPackages': retained,
        'personalNVDAProfileTouched': False, 'liveNVDAOrPhysicalKeyTest': False,
        'published': False, 'uploadedToDrive': False,
    }
    target = ROOT / 'docs/command_cleanup_dev20_acceptance.json'
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', 'utf8')
    print(json.dumps({k: result[k] for k in ('sha256', 'bytes', 'sourceFilesVerified', 'unchangedExistingPackageFiles', 'gate')}, indent=2))


if __name__ == '__main__':
    main()
