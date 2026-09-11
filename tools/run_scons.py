"""Run the workspace-local SCons installation without changing PYTHONPATH."""

from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
BUILD_DEPENDENCIES = ROOT / ".build-deps"
if not BUILD_DEPENDENCIES.is_dir():
	raise SystemExit(
		"Build dependencies are missing. Run: "
		"python -m pip install --requirement requirements-build.txt --target .build-deps"
	)

sys.path.insert(0, str(BUILD_DEPENDENCIES))

from SCons.Script import main  # noqa: E402


if __name__ == "__main__":
	main()
