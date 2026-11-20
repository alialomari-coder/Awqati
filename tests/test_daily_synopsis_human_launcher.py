"""New acceptance-launcher safety checks only; no existing add-on suites."""
import importlib.util
from pathlib import Path
import hashlib
import json
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('human_launcher',ROOT/'tools/run_daily_synopsis_human_acceptance.py')
launcher=importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


class DesktopReturnSafetyTests(unittest.TestCase):
    def test_unapproved_extra_source_file_blocks_launch(self):
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder)
            (base/'addon').mkdir()
            (base/'human_host.py').write_bytes(b'approved')
            (base/'addon/unapproved.py').write_bytes(b'extra')
            (base/'manifest.json').write_text(json.dumps(dict(files={'human_host.py':hashlib.sha256(b'approved').hexdigest()},runtime=str(base),runtimeFiles={})))
            with patch.object(launcher,'BASE',base):
                with self.assertRaisesRegex(RuntimeError,'inventory mismatch'):
                    launcher.verified_manifest()

    def test_locked_desktop_is_not_bypassed(self):
        api=Mock()
        with patch.object(launcher,'current_desktop',return_value=None):
            self.assertFalse(launcher.restore(api,123,'AwqatiHuman32_test'))
        api.SwitchDesktop.assert_not_called()

    def test_normal_desktop_already_active_needs_no_switch(self):
        api=Mock()
        with patch.object(launcher,'current_desktop',return_value='Default'):
            self.assertTrue(launcher.restore(api,123,'AwqatiHuman32_test'))
        api.SwitchDesktop.assert_not_called()

    def test_unrelated_desktop_is_not_stolen(self):
        api=Mock()
        with patch.object(launcher,'current_desktop',return_value='AnotherApplicationDesktop'):
            self.assertTrue(launcher.restore(api,123,'AwqatiHuman32_test'))
        api.SwitchDesktop.assert_not_called()

    def test_only_our_own_desktop_returns_to_original_handle(self):
        api=Mock();api.SwitchDesktop.return_value=1
        with patch.object(launcher,'current_desktop',return_value='AwqatiHuman32_test'):
            self.assertTrue(launcher.restore(api,123,'AwqatiHuman32_test'))
        api.SwitchDesktop.assert_called_once_with(123)

    def test_return_failure_is_not_reported_as_success(self):
        api=Mock();api.SwitchDesktop.return_value=0
        with patch.object(launcher,'current_desktop',return_value='AwqatiHuman32_test'):
            self.assertFalse(launcher.restore(api,123,'AwqatiHuman32_test'))


if __name__=='__main__':unittest.main()
