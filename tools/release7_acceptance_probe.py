"""Extend existing real-NVDA integration with built-artifact and upgrade checks."""
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys
import addonHandler
import globalVars

PROFILE = Path(globalVars.appArgs.configPath)
ROOT = Path((PROFILE / 'source-root.txt').read_text('utf-8'))
sys.path.insert(0, str(ROOT / 'tools'))
from converter_integration_nvda_probe import GlobalPlugin as IntegrationProbe
from release7_install_probe import settings_snapshot


class GlobalPlugin(IntegrationProbe):
	def begin(self):
		addon = next(a for a in addonHandler.getAvailableAddons() if a.name == 'awqati')
		self.require(addon.manifest['version'] == '7.0.0' and addon.isRunning, 'installed 7.0.0 running after real restart')
		self.require(not addon.isPendingInstall and not addon.isPendingRemove, 'no pending install or removal remains')
		inventory = json.loads((self.profile / 'package-inventory.json').read_text('utf-8'))
		for name, expected in inventory.items():
			self.require(hashlib.sha256((Path(addon.path) / name).read_bytes()).hexdigest() == expected, 'installed artifact hash: ' + name)
		old = self.profile / 'old-runtime-settings.json'
		if old.exists():
			import globalPluginHandler
			plugin = next(p for p in globalPluginHandler.runningPlugins if p.__module__.endswith('awqati.nvda_adapter.plugin'))
			actual = settings_snapshot(plugin._context.settings.runtime_settings)
			self.require(actual == old.read_text('utf-8'), 'all 6.0.0 runtime settings survive upgrade unchanged')
		super().begin()
