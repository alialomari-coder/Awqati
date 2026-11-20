"""Regression for the real custom-location/AUTO request failure found in NVDA."""
import ast
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace as NS
import sys
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'addon/globalPlugins'))
from awqati.domain import CalculationMethod, LocationKind, StoredLocation, Location, default_settings
from awqati.infrastructure import BundledCalculationMethodRepository


class CustomCalculationChoiceTests(unittest.TestCase):
    def setUp(self):
        tree = ast.parse((ROOT/'addon/globalPlugins/awqati/nvda_adapter/ui.py').read_text('utf8'))
        funcs = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in
                 ('custom_calculation_method_required', 'choose_custom_calculation_method')]
        self.dialog = Mock()
        self.dialog.ShowModal.return_value = 1
        self.dialog.GetSelection.return_value = 1
        self.wx = NS(SingleChoiceDialog=Mock(return_value=self.dialog), ID_OK=1, NOT_FOUND=-1)
        self.ns = {'wx':self.wx, '_':lambda t:t, 'CalculationMethod':CalculationMethod,
                   'LocationKind':LocationKind, 'BundledCalculationMethodRepository':BundledCalculationMethodRepository}
        exec(compile(ast.Module(body=funcs, type_ignores=[]), 'actual UI choice', 'exec'), self.ns)
        self.settings = default_settings()
        self.settings.location = StoredLocation(LocationKind.CUSTOM, Location('test','Test',24.6877,46.7219,'Asia/Riyadh'))

    def choose(self):
        return self.ns['choose_custom_calculation_method'](None, self.settings)

    def test_custom_auto_requires_explicit_choice_and_offers_no_auto_option(self):
        self.assertTrue(self.choose())
        self.assertNotEqual(self.settings.prayer.calculation_method, CalculationMethod.AUTO)
        self.dialog.SetSelection.assert_called_once_with(0)
        labels = self.wx.SingleChoiceDialog.call_args.args[3]
        self.assertEqual(len(labels), len(CalculationMethod))
        self.dialog.Destroy.assert_called_once()

    def test_cancel_preserves_every_setting(self):
        before = deepcopy(self.settings)
        self.dialog.ShowModal.return_value = 0
        self.assertFalse(self.choose())
        self.assertEqual(before, self.settings)
        self.dialog.Destroy.assert_called_once()

    def test_no_selection_does_not_guess_a_method(self):
        self.dialog.GetSelection.return_value = 0
        self.assertFalse(self.choose())
        self.assertEqual(CalculationMethod.AUTO, self.settings.prayer.calculation_method)

    def test_existing_manual_choice_is_preserved_without_prompt(self):
        self.settings.prayer.calculation_method = CalculationMethod.MAKKAH
        self.assertTrue(self.choose())
        self.wx.SingleChoiceDialog.assert_not_called()

    def test_country_auto_and_missing_location_are_unchanged_without_prompt(self):
        self.settings.location.kind = LocationKind.SELECTED
        self.settings.location.country_code = 'SA'
        self.assertTrue(self.choose())
        self.settings.location = None
        self.assertTrue(self.choose())
        self.wx.SingleChoiceDialog.assert_not_called()
