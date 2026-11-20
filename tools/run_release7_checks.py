"""Full release gate using the existing embedded interpreter, no installation.

The temporary interpreter supplies import paths to subprocess regression tests.
All repository checks, including clean/build/package tests, remain enabled.
"""
from pathlib import Path
import json
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'docs/historical_converter_task6'


def worker():
	sys.path[:0] = [str(ROOT), str(ROOT / 'tools'), str(ROOT / 'tests'), str(ROOT / 'addon/globalPlugins')]
	from tools import run_checks
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
	commands[3] = (commands[3][0], (sys.executable, '-B', str(Path(__file__).resolve()), '--worker', '--suite'))
	run_checks._require_build_dependencies()
	for i, stage in enumerate(commands):
		run_checks._run_command(*stage)
		if i == 1:
			run_checks._verify_clean_outputs()
	return 0


def main():
	OUTPUT.mkdir(parents=True, exist_ok=True)
	if '--worker' in sys.argv:
		return worker()
	installation = Path(sys.executable).resolve().parent
	pth = installation / f'python{sys.version_info.major}{sys.version_info.minor}._pth'
	with tempfile.TemporaryDirectory(prefix='release7-checks-') as directory:
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
