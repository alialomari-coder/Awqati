"""Use NVDA's actual add-on installer only in a guarded synthetic profile."""
from dataclasses import asdict
import importlib
import json
from pathlib import Path
import traceback
import addonHandler
import core
import globalPluginHandler
import globalVars
import systemUtils
import versionInfo
import wx


def settings_snapshot(settings):
	from enum import Enum
	def neutral(value):
		if isinstance(value, Enum):
			return value.value
		if isinstance(value, dict):
			return {str(neutral(k)): neutral(v) for k, v in value.items()}
		if isinstance(value, (list, tuple)):
			return [neutral(v) for v in value]
		return value
	return json.dumps(neutral(asdict(settings)), default=str, ensure_ascii=False, sort_keys=True)


class GlobalPlugin(globalPluginHandler.GlobalPlugin):
	def __init__(self):
		super().__init__()
		self.profile = Path(globalVars.appArgs.configPath)
		if not self.profile.name.startswith('task3-live-task5-release7-'):
			raise RuntimeError('Private release7 profile required')
		wx.CallLater(3000, self.run)

	def run(self):
		result = dict(passed=False, nvda=versionInfo.version, checks=[])
		try:
			assert systemUtils._getDesktopName().startswith('AwqatiTask3_')
			instruction = json.loads((self.profile / 'install-instruction.json').read_text('utf-8'))
			addons = [a for a in addonHandler.getAvailableAddons() if a.name == 'awqati']
			if instruction['oldVersion']:
				assert len(addons) == 1 and addons[0].manifest['version'] == instruction['oldVersion']
				plugin = next(p for p in globalPluginHandler.runningPlugins if p.__module__.endswith('awqati.nvda_adapter.plugin'))
				assert plugin._runtime is not None
				(self.profile / 'old-runtime-settings.json').write_text(settings_snapshot(plugin._context.settings.runtime_settings), 'utf-8')
				result['checks'].append('6.0.0 loaded and runtime settings captured before real upgrade')
				addons[0].requestRemove()
			else:
				assert not addons
			bundle = addonHandler.AddonBundle(instruction['package'])
			assert bundle.manifest['version'] == '7.0.0'
			addon = addonHandler.installAddonBundle(bundle)
			assert addon is not None and not bundle._installExceptions
			assert addon.isPendingInstall
			result['checks'].append('7.0.0 bundle accepted by real NVDA installer, pending restart')
			result['passed'] = True
		except Exception:
			result['error'] = traceback.format_exc()
		(self.profile / 'live-result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), 'utf-8')
		wx.CallLater(200, core.triggerNVDAExit)
