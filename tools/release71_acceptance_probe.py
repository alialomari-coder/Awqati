"""Installed 7.1.0 artifact: synopsis, accessibility and core command checks."""
import hashlib
import importlib
import json
import sys
from pathlib import Path
import addonHandler
import globalVars
import inputCore
import keyboardHandler
import scriptHandler

PROFILE=Path(globalVars.appArgs.configPath)
ROOT=Path((PROFILE/'source-root.txt').read_text('utf-8'))
sys.path.insert(0,str(ROOT/'tools'))
from daily_synopsis_nvda_probe import GlobalPlugin as SynopsisProbe
from release7_install_probe import settings_snapshot


class GlobalPlugin(SynopsisProbe):
    def begin(self):
        addon=next(a for a in addonHandler.getAvailableAddons() if a.name=='awqati')
        self.require(addon.manifest['version']=='7.1.0' and addon.isRunning,'installed 7.1.0 running after real restart')
        self.require(not addon.isPendingInstall and not addon.isPendingRemove,'installation committed without pending state')
        inventory=json.loads((self.profile/'package-inventory.json').read_text('utf-8'))
        mismatches=[name for name,sha in inventory.items()
            if hashlib.sha256((Path(addon.path)/name).read_bytes()).hexdigest()!=sha]
        self.require(not mismatches,'every installed artifact file matches final package SHA-256')
        self.result['installedFilesVerified']=len(inventory)
        self.addon_root=Path(addon.path).resolve()
        super().begin()
        module=importlib.import_module(self.plugin.__module__)
        self.require(Path(module.__file__).resolve().is_relative_to(self.addon_root),'plugin loaded from installed artifact rather than development source')
        old=self.profile/'old-runtime-settings.json'
        if old.exists():
            self.require(settings_snapshot(self.plugin._context.settings.runtime_settings)==old.read_text('utf-8'),
                'all runtime settings survive real 7.0.0 to 7.1.0 upgrade')

    def scenarios(self):
        yield from super().scenarios()
        # Existing actual composition, without toggling or saving any settings.
        for attr in ('_converter','_stopwatch','_countdowns','_world_clock','_on_this_day'):
            self.require(getattr(self.plugin,attr) is not None,'existing function initialized '+attr)
        for key,script in (
            ('NVDA+f11',self.plugin.script_prayerInfo),
            ('NVDA+h',self.plugin.script_hijriCalendars),
            ('NVDA+alt+f12',self.plugin.script_alertStatus)):
            gesture=keyboardHandler.KeyboardInputGesture.fromName(key)
            self.require(scriptHandler.findScript(gesture)==script,'core artifact gesture binding '+key)
            scriptHandler.clearLastScript()
            start=len(self.messages)
            inputCore.manager.executeGesture(gesture)
            yield 180
            self.require(len(self.messages)>start and bool(self.messages[-1]),'core artifact command speaks '+key)
        self.require(bool(self.content.qibla_text(self.language)),'installed artifact Qibla remains available')
