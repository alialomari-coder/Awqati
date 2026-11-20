"""Full release gate using the existing embedded interpreter, no installation.

The temporary interpreter supplies import paths to subprocess regression tests.
All repository checks, including clean/build/package tests, remain enabled.
"""
from pathlib import Path
import json
import hashlib
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'docs/release_7_1_0'
if '--closure' in sys.argv:
	OUTPUT = OUTPUT / 'closure/gate'
if '--closure-smoke' in sys.argv:
	OUTPUT = ROOT / 'docs/release_7_1_0/closure/resumed_verification'


def worker():
	sys.path[:0] = [str(ROOT), str(ROOT / 'tools'), str(ROOT / 'tests'), str(ROOT / 'addon/globalPlugins')]
	from tools import run_checks
	if '--closure-smoke' in sys.argv:
		package = ROOT / 'dist/awqati-7.1.0.nvda-addon'
		before = hashlib.sha256(package.read_bytes()).hexdigest()
		assert list((ROOT / 'dist').iterdir()) == [package]
		for path in list((ROOT / 'addon').rglob('*.py')) + list((ROOT / 'tools').glob('*release71*.py')):
			compile(path.read_bytes(), str(path), 'exec')
		suite = unittest.defaultTestLoader.loadTestsFromNames([
			'test_release_package', 'test_final_help', 'test_architecture'])
		with (OUTPUT / 'suite.log').open('w', encoding='utf-8') as stream:
			result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
		assert hashlib.sha256(package.read_bytes()).hexdigest() == before
		summary = dict(tests=result.testsRun, failures=len(result.failures), errors=len(result.errors),
			skipped=len(result.skipped), successful=result.wasSuccessful(), packageUnchanged=True,
			referenceAstronomyTestsRerun=False, rebuilt=False)
		(OUTPUT / 'test_summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
		print(json.dumps(summary), flush=True)
		return int(not result.wasSuccessful())
	# Preserve the complete suite result as machine-readable evidence as well.
	if '--suite' in sys.argv:
		suite = unittest.defaultTestLoader.discover(str(ROOT / 'tests'))
		with (OUTPUT / 'suite.log').open('w', encoding='utf-8') as stream:
			result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
		summary = dict(python=sys.version, tests=result.testsRun, failures=len(result.failures),
			errors=len(result.errors), skipped=len(result.skipped), successful=result.wasSuccessful(),
			skipReasons=[str(reason) for _, reason in result.skipped])
		(OUTPUT / 'test_summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
		print(json.dumps(summary), flush=True)
		return int(not result.wasSuccessful())
	commands = list(run_checks._commands())
	commands[3] = (commands[3][0], (sys.executable, '-B', str(Path(__file__).resolve()), '--worker', '--suite',
		*(['--closure'] if '--closure' in sys.argv else [])))
	run_checks._require_build_dependencies()
	existing = '--verify-existing-package' in sys.argv
	package = ROOT / 'dist/awqati-7.1.0.nvda-addon'
	before = hashlib.sha256(package.read_bytes()).hexdigest() if existing else None
	if existing:
		print('Reuse successful initial clean/build; verify unchanged artifact during the final checks.', flush=True)
		commands = [commands[0], commands[3], commands[4]]
	for i, stage in enumerate(commands):
		run_checks._run_command(*stage)
		if i == 1 and not existing:
			run_checks._verify_clean_outputs()
	if existing:
		assert hashlib.sha256(package.read_bytes()).hexdigest() == before
	return 0


def main():
	OUTPUT.mkdir(parents=True, exist_ok=True)
	if '--worker' in sys.argv:
		return worker()
	installation = Path(sys.executable).resolve().parent
	pth = installation / f'python{sys.version_info.major}{sys.version_info.minor}._pth'
	with tempfile.TemporaryDirectory(prefix='release71-checks-') as directory:
		directory = Path(directory)
		shutil.copy2(sys.executable, directory / 'python.exe')
		for dll in installation.glob('*.dll'):
			shutil.copy2(dll, directory / dll.name)
		paths = [str((installation / line).resolve()) for line in pth.read_text().splitlines()
			if line.strip() and not line.startswith(('#', 'import '))]
		paths += [str(ROOT), str(ROOT / 'tests'), str(ROOT / 'addon/globalPlugins')]
		(directory / pth.name).write_text('\n'.join(paths) + '\n', encoding='utf-8')
		with (OUTPUT / 'gate.log').open('w', encoding='utf-8') as log:
			return subprocess.run([str(directory / 'python.exe'), '-B', str(Path(__file__).resolve()),
				'--worker', *sys.argv[1:]], cwd=ROOT, stdout=log, stderr=subprocess.STDOUT).returncode


if __name__ == '__main__':
	raise SystemExit(main())
