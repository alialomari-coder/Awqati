"""NVDA lifecycle, native repeat dispatch boundary and background manual updates."""
from datetime import datetime, timezone
from pathlib import Path
from threading import Thread, Event
from zipfile import BadZipFile
import json
import addonHandler
import languageHandler
import ui
import wx
from ..application.world_clock import WorldClockService, describe_city
from ..application.world_clock_updates import WorldUpdatePolicy
from ..domain import ClockType
from ..infrastructure.stopwatch import StopwatchRepository
from ..infrastructure.windows_local_time import WindowsLocalTimezone
from ..infrastructure.world_clock import load_data, active_root, WorldClockUpdater, WorldDataError, WorldDataIncompatible

addonHandler.initTranslation()


class WorldClockControl:
    def __init__(self, root, runtime, addon_root):
        self.runtime,self.dialog,self.service=runtime,None,None
        self.bundled=Path(addon_root)/'data/world_clock'
        self.user=Path(root)/'world_clock'
        self.repository=StopwatchRepository(Path(root)/'world_clock_cities.json')
        self.closed=Event();self.updating=False;self.selected_id=None
        self.auto_job=None;self.notice_job=None
        self.policy=WorldUpdatePolicy(StopwatchRepository(Path(root)/'world_clock_updates.json'))
        try:
            self.reload()
        except (OSError,ValueError,KeyError,TypeError):
            self.repository.read_only=True
            wx.CallAfter(ui.message, _('World clock data could not be read. Existing files were preserved.'))
        if self.service is not None:self.schedule_auto()

    def reload(self, prepared=None):
        if prepared is None:
            root=active_root(self.bundled,self.user)
            catalog,zones,metadata=load_data(root)
            mapping=json.loads((root/'timezones/windows_zones.json').read_text('utf8'))
        else:catalog,zones,metadata,mapping=prepared
        local=WindowsLocalTimezone()
        updater=getattr(self,'updater',None) or WorldClockUpdater(self.bundled,self.user)
        if self.service is None:
            service=WorldClockService(catalog,self.repository)
        else:
            service=self.service
            # Unknown IDs retain their last valid localized record.
            rows=tuple(catalog.cities.get(c.city_id,c) for c in service.rows)
            service.catalog,service.rows=catalog,rows
        self.service,self.zones,self.local,self.metadata=service,zones,local,metadata
        self.updater=updater

    @staticmethod
    def language():
        return 'ar' if languageHandler.getLanguage().replace('_','-').split('-')[0]=='ar' else 'en'

    def text(self, city):
        presentation=self.runtime.settings.runtime_settings.clock.presentations[ClockType.ZAWALI]
        instant=datetime.now(timezone.utc)
        return describe_city(city,instant,self.zones,self.local(instant),self.language(),presentation,self.service.display(city,self.language()))

    def city_name(self,city):
        return self.service.display(city,self.language())[0]

    def announce(self,index):
        if self.closed.is_set():return
        if self.service is None:
            ui.message(_('World clock data could not be read. Existing files were preserved.'));return
        if not self.service.rows:ui.message(_('No city has been added yet.'));return
        city=self.service.first(index)
        if city is None:
            ui.message(_('There is no second city.') if index==1 else _('There is no third city.'));return
        try:ui.message(self.text(city))
        except (OSError,ValueError,KeyError):ui.message(_('The city time is unavailable. Existing data were preserved.'))

    def refresh(self, city_id=None):
        if city_id is not None:self.selected_id=city_id
        if self.dialog:self.dialog.refresh()

    def save_error(self):
        ui.message(_('The city list could not be saved. The previous list was preserved.'))

    def add(self,city):
        try:
            added=self.service.add(city)
        except (OSError,ValueError):self.save_error();return
        self.refresh(city.city_id if added else None)
        ui.message((_('Added {city}.') if added else _('{city} is already in your list.')).format(city=self.city_name(city)))

    def schedule_auto(self):
        if self.auto_job:self.auto_job.Stop();self.auto_job=None
        if self.closed.is_set() or not self.policy.enabled:return
        delay=max(60,int(self.policy.deadline()-self.policy.clock()))
        # One deadline, not a timer that polls repeatedly for the due date.
        self.auto_job=wx.CallLater(min(delay*1000,2147483000),self.auto_check)

    def auto_check(self):
        self.auto_job=None
        if self.closed.is_set() or not self.policy.enabled:return
        if self.policy.due():self.update(automatic=True)
        else:self.schedule_auto()

    def set_automatic(self,enabled):
        try:self.policy.set_enabled(enabled)
        except (OSError,ValueError):
            ui.message(_('World clock update settings could not be saved.'));return False
        self.schedule_auto();return True

    def updated_notice(self,attempt=0):
        if self.closed.is_set():return
        presenter=getattr(self.runtime,'presenter',None)
        scheduler=getattr(self.runtime,'scheduler',None)
        audio=getattr(self.runtime,'audio',None)
        if any(getattr(obj,field,None) for obj,field in ((presenter,'current'),(scheduler,'current'),(scheduler,'waiting'),(audio,'busy'))):
            if attempt<120:self.notice_job=wx.CallLater(5000,lambda:self.updated_notice(attempt+1))
            return
        from speech.priorities import Spri
        ui.message(_('World clock data updated.'),speechPriority=Spri.NEXT)

    def update(self,automatic=False):
        if self.updating or self.closed.is_set() or self.service is None:return
        policy=getattr(self,'policy',None)
        if automatic and (policy is None or not policy.enabled):return
        self.updating=True
        if not automatic:ui.message(_('Checking world clock data updates.'))
        def worker():
            old=None;activated=False;prepared=None
            cancelled=lambda:self.closed.is_set() or bool(automatic and not policy.enabled)
            try:
                target=self.updater.check(self.service.catalog.version,cancelled)
                outcome='unchanged' if target is None else 'ready'
                if target is not None:
                    catalog,zones,metadata=load_data(target)
                    mapping=json.loads((target/'timezones/windows_zones.json').read_text('utf8'))
                    prepared=(catalog,zones,metadata,mapping)
                    if cancelled():raise InterruptedError('Automatic check cancelled')
                    try:old=self.updater.activate(target);activated=True
                    except OSError as error:raise WorldDataError('Update activation failed') from error
            except Exception as error:
                incompatible=globals().get('WorldDataIncompatible',())
                outcome=('incompatible' if isinstance(error,incompatible) else 'cancelled' if isinstance(error,InterruptedError) and cancelled() else
                    'network' if isinstance(error,OSError) and not isinstance(error,BadZipFile) else 'invalid')
                if policy and outcome!='cancelled':
                    try:policy.failure(type(error).__name__+': '+str(error))
                    except (OSError,ValueError):pass
                try:
                    from logHandler import log
                    log.debugWarning('Awqati world-clock update: '+type(error).__name__+': '+str(error))
                except ImportError:pass
                target=None
            if cancelled():
                if activated:
                    try:self.updater.rollback(old)
                    except OSError:pass
                self.updating=False;return
            def finish():
                if self.closed.is_set():return
                self.updating=False
                if automatic and not policy.enabled:
                    if activated:
                        try:self.updater.rollback(old)
                        except OSError:pass
                    return
                if outcome=='ready':
                    try:
                        self.reload(prepared);self.refresh()
                    except Exception:
                        if activated:
                            try:self.updater.rollback(old)
                            except OSError:pass
                        if policy:
                            try:policy.failure('GUI adoption failed; previous data restored')
                            except (OSError,ValueError):pass
                        if not automatic:ui.message(_('The update could not be verified. The previous data were retained.'))
                        if policy:self.schedule_auto()
                        return
                    if automatic:self.updated_notice()
                    else:ui.message(_('World clock data updated.'))
                elif not automatic:
                    ui.message({'unchanged':_('World clock data are up to date.'),
                        'network':_('Could not connect to the update service. No data were changed.'),
                        'invalid':_('The update could not be verified. The previous data were retained.'),
                        'incompatible':_('This data update requires a newer version of Awqati. No data were changed.')}[outcome])
                if policy:
                    if outcome in ('ready','unchanged'):
                        # Small isolated state write, not the data download/verification.
                        try:policy.success(outcome=='ready')
                        except (OSError,ValueError):pass
                    self.schedule_auto()
            if self.closed.is_set():return
            try:wx.CallAfter(finish)
            except RuntimeError:
                # The wx application can disappear while NVDA is shutting down.
                self.updating=False
        Thread(target=worker,name='AwqatiWorldClockUpdate',daemon=True).start()

    def close(self):
        self.closed.set();self.dialog=None
        for job in (getattr(self,'auto_job',None),getattr(self,'notice_job',None)):
            if job:job.Stop()
