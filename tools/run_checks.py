"""Run Awqati's required local checks through one deterministic entry point."""

from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import sys
from typing import Sequence


ROOT = Path(__file__).resolve().parents[1]
BUILD_DEPENDENCIES = ROOT / ".build-deps"
BUILD_OUTPUTS = (ROOT / "build", ROOT / "dist")


class CheckFailed(RuntimeError):
	"""Raised when a required check cannot complete successfully."""


def _run_command(name: str, command: Sequence[str]) -> None:
	print(f"\n== {name} ==", flush=True)
	result = subprocess.run(command, cwd=ROOT, check=False)
	if result.returncode:
		raise CheckFailed(f"{name} failed with exit code {result.returncode}")


def _require_build_dependencies() -> None:
	if not BUILD_DEPENDENCIES.is_dir():
		raise CheckFailed(
			"Build dependencies are missing. Run: "
			"python -m pip install --requirement requirements-build.txt --target .build-deps"
		)


def _verify_clean_outputs() -> None:
	print("\n== verify clean build outputs ==", flush=True)
	remaining = [path.relative_to(ROOT) for path in BUILD_OUTPUTS if path.exists()]
	if remaining:
		raise CheckFailed("SCons clean left build outputs behind: " + ", ".join(map(str, remaining)))


def _commands() -> tuple[tuple[str, tuple[str, ...]], ...]:
	python = sys.executable
	return (
		(
			"compile and validation",
			(
				python,
				"-m",
				"compileall",
				"-q",
				"addon",
				"tests",
				"buildVars.py",
				"tools/run_scons.py",
				"tools/run_checks.py",
			),
		),
		("clean build", (python, "tools/run_scons.py", "-c")),
		("build package", (python, "tools/run_scons.py")),
		(
			"unit, import, architecture, and package verification tests",
			(python, "-m", "unittest", "discover", "-s", "tests", "-v"),
		),
		("repository whitespace check", ("git", "diff", "--check")),
	)


def main() -> int:
	try:
		_require_build_dependencies()
		if shutil.which("git") is None:
			raise CheckFailed("Git is required for the repository whitespace check")
		commands = _commands()
		_run_command(*commands[0])
		_run_command(*commands[1])
		_verify_clean_outputs()
		for stage in commands[2:]:
			_run_command(*stage)
	except CheckFailed as error:
		print(f"\nCHECKS FAILED: {error}", file=sys.stderr, flush=True)
		return 1
	print("\nALL REQUIRED CHECKS PASSED", flush=True)
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
