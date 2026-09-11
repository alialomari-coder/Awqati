from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
	sys.path.insert(0, str(ROOT))

from tools import run_checks  # noqa: E402


class RunChecksTests(unittest.TestCase):
	def test_every_python_stage_uses_the_current_interpreter(self) -> None:
		python_commands = [command for _, command in run_checks._commands() if command[0] != "git"]
		self.assertTrue(python_commands)
		self.assertTrue(all(command[0] == sys.executable for command in python_commands))

	def test_a_failed_required_command_stops_the_runner(self) -> None:
		failure = subprocess.CompletedProcess([sys.executable, "-c", "pass"], returncode=7)
		with patch.object(run_checks.subprocess, "run", return_value=failure):
			with self.assertRaisesRegex(run_checks.CheckFailed, "exit code 7"):
				run_checks._run_command("deliberate failure", failure.args)

	def test_clean_verification_rejects_any_remaining_output(self) -> None:
		with patch.object(run_checks, "BUILD_OUTPUTS", (ROOT,)):
			with self.assertRaisesRegex(run_checks.CheckFailed, "left build outputs"):
				run_checks._verify_clean_outputs()


if __name__ == "__main__":
	unittest.main()
