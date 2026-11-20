"""Standalone real-wx integration probe; no personal NVDA settings are accessed.

Requires wxPython on PYTHONPATH. NVDA APIs are injected test boundaries;
this is not a claim of speech, braille or in-process NVDA acceptance.
"""
import ast
import ctypes
import gettext
import json
import os
from pathlib import Path
import sys
import tempfile
import subprocess
from datetime import datetime, timezone
from threading import Event, Thread
from zipfile import BadZipFile
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'tests'), str(ROOT/'addon/globalPlugins')]
import wx
from time_tools_driver import definitions
from awqati.nvda_adapter.settings_sections import is_rtl_language
from awqati.nvda_adapter.stopwatch_formatter import numeric, MODE_LABELS, STATE_LABELS as WATCH_STATES, ACTION_LABELS
from awqati.nvda_adapter.countdown_formatter import STATE_LABELS as TIMER_STATES
from test_stopwatch import Clock, MemoryRepository, Stopwatch
from test_countdown import Memory, CountdownService, Countdown
from msaa_probe import native_list_properties, NativePropertyServices, NAME_PROPERTY
from awqati.application.world_clock import WorldClockService, describe_city
from awqati.application.world_clock_updates import WorldUpdatePolicy
from awqati.infrastructure.world_clock import load_data, active_root, WorldClockUpdater, WorldDataError, WorldDataIncompatible
from awqati.infrastructure.windows_local_time import WindowsLocalTimezone
from awqati.infrastructure.stopwatch import StopwatchRepository
from awqati.domain import ClockType, ClockPresentationSettings
from ctypes import byref


def require(condition, detail):
    if not condition:
        raise RuntimeError(detail)


def run(language):
    translate = gettext.translation('nvda', ROOT/'build/awqati/locale', languages=[language], fallback=True).gettext
    direction = lambda window: window.SetLayoutDirection(wx.Layout_RightToLeft if language=='ar' else wx.Layout_LeftToRight)
    namespace = {'wx':wx, '_':translate, 'languageHandler':SimpleNamespace(getLanguage=lambda:language),
        'is_rtl_language':is_rtl_language, 'numeric':numeric, 'MODE_LABELS':MODE_LABELS,
        'STATE_LABELS':WATCH_STATES, 'ACTION_LABELS':ACTION_LABELS}
    definitions('stopwatch_dialog.py',namespace,{'StopwatchDialog'})
    namespace['STATE_LABELS']=TIMER_STATES; namespace['direction']=direction
    # Function globals must remain independent between the three original views.
    countdown_ns=namespace.copy(); definitions('countdown_dialog.py',countdown_ns,{'CountdownDialog','duration'})
    property_services = NativePropertyServices()
    native_ns = {'wx':wx, 'byref':byref, 'oleacc':SimpleNamespace(PROPID_ACC_NAME=NAME_PROPERTY),
        'IAccessibleHandler':SimpleNamespace(accPropServices=property_services)}
    definitions('native_accessibility.py',native_ns,{'set_list_name'})
    countdown_ns['set_list_name'] = native_ns['set_list_name']
    alarm_ns={'wx':wx,'_':translate, 'set_direction':direction}
    definitions('alarm_dialogs.py',alarm_ns,{'AlarmManager'})
    # The stopwatch globals use their original state label map.
    namespace['STATE_LABELS']=WATCH_STATES
    host_ns={'wx':wx,'_':translate,'AlarmManager':alarm_ns['AlarmManager'],
        'CountdownDialog':countdown_ns['CountdownDialog'],'StopwatchDialog':namespace['StopwatchDialog']}
    definitions('time_tools.py',host_ns)
    clock=Clock(); watch_repo=MemoryRepository(); watch=Stopwatch(clock,watch_repo); watch.toggle()
    timer_repo=Memory(); service=CountdownService(clock,lambda:1800000000,timer_repo)
    first,second=Countdown.create('First',90),Countdown.create('Second',120,saved=True)
    for timer in (first,second): service.put(timer); service.transition(timer.timer_id,'start')
    runtime=SimpleNamespace(alarms=SimpleNamespace(storage_error=False,alarms={}),now=SimpleNamespace(now=lambda:None),
        scheduler=SimpleNamespace(has_pending=lambda scope:False))
    actions=[]
    watch_control=SimpleNamespace(watch=watch,mode=2,dialog=None)
    for method in ('toggle','lap','reset','copy','preview','cancel_feedback'):
        setattr(watch_control,method,lambda *a,m=method:actions.append(m))
    watch_control.set_mode=lambda mode:True
    timers=SimpleNamespace(service=service,selected=first.timer_id,dialog=None,runtime=runtime)
    for method in ('toggle','change','restart','stop_alert','announce','preview'):
        setattr(timers,method,lambda *a,m=method:actions.append(m))
    world_temp=tempfile.TemporaryDirectory();messages=[]
    runtime.settings=SimpleNamespace(runtime_settings=SimpleNamespace(clock=SimpleNamespace(
        presentations={ClockType.ZAWALI:ClockPresentationSettings()})))
    world_ns={'wx':wx,'_':translate,'ui':SimpleNamespace(message=messages.append),'languageHandler':SimpleNamespace(getLanguage=lambda:language),
        'Event':Event,'Thread':Thread,'Path':Path,'json':json,'datetime':datetime,'timezone':timezone,
        'WorldClockService':WorldClockService,'WorldUpdatePolicy':WorldUpdatePolicy,'describe_city':describe_city,'ClockType':ClockType,
        'StopwatchRepository':StopwatchRepository,'WindowsLocalTimezone':WindowsLocalTimezone,
        'load_data':load_data,'active_root':active_root,'WorldClockUpdater':WorldClockUpdater,'WorldDataError':WorldDataError,'WorldDataIncompatible':WorldDataIncompatible,'BadZipFile':BadZipFile}
    definitions('world_clock_control.py',world_ns)
    world=world_ns['WorldClockControl'](Path(world_temp.name),runtime,ROOT/'addon/globalPlugins/awqati')
    require(world.service is not None,'offline world-clock loading')
    for city in ('London','Tokyo','Cairo'):world.add(world.service.catalog.search(city)[0])
    world_view_ns={'wx':wx,'_':translate,'ui':SimpleNamespace(message=messages.append),'direction':direction,
        'set_list_name':native_ns['set_list_name']}
    definitions('world_clock_dialog.py',world_view_ns)
    host_ns['WorldClockPanel']=world_view_ns['WorldClockPanel']
    frame=wx.Frame(None,title='Awqati isolated wx probe',size=(900,800)); direction(frame)
    parent=wx.Panel(frame); box=wx.BoxSizer(wx.VERTICAL); parent.SetSizer(box)
    frame_box=wx.BoxSizer(wx.VERTICAL); frame_box.Add(parent,1,wx.EXPAND); frame.SetSizer(frame_box)
    state=host_ns['TimeToolsState'](runtime,timers,watch_control,world)
    host=host_ns['TimeToolsHost'](parent,box,state,lambda:parent.Layout())
    frame.Show(); wx.Yield()
    expected=('المنبهات','المؤقتات','ساعة الإيقاف','الساعة العالمية') if language=='ar' else ('Alarms','Timers','Stopwatch','World clock')
    require(tuple(host.choice.GetStrings())==expected,'translated choice labels')
    for tool in ('alarms','timers','stopwatch','world_clock','timers','alarms','stopwatch'):
        host.select(tool); wx.Yield()
        require(wx.Window.FindFocus() is host.choice,'selector focus')
        for identity,view in host.views.items():
            require(view.IsShownOnScreen()==(identity==tool),'native visibility')
            require(view.GetLayoutDirection()==(wx.Layout_RightToLeft if language=='ar' else wx.Layout_LeftToRight),'native direction')
        # Exercise actual Windows tab navigation in both directions.
        host.choice.Navigate(wx.NavigationKeyEvent.IsForward); wx.Yield()
        focused=wx.Window.FindFocus(); view=host.views[tool]
        require(view.IsDescendant(focused),'Tab enters selected view only')
        focused.Navigate(wx.NavigationKeyEvent.IsBackward); wx.Yield()
        require(wx.Window.FindFocus() is host.choice,'Shift+Tab returns to selector')
        host.choice.SetFocus()
    timer_view=host.views['timers']; stopwatch_view=host.views['stopwatch']
    native_timer = native_list_properties(timer_view.list.GetHandle())
    require(native_timer == {'name':translate('Timers list'), 'role':33}, 'native MSAA timer list name and role: '+repr(native_timer))
    native_row = native_list_properties(timer_view.list.GetHandle(), 1)
    require(translate('Timers list') not in native_row['name'] and native_row['name'], 'row retains its own name without list-name repetition')
    timer_view.list.Select(0); timer_view.list.Focus(0); wx.Yield()
    selected=timers.selected; native_selected=timer_view.list.GetFirstSelected()
    host.select('stopwatch'); clock.advance(5); host.select('timers'); timer_view.refresh()
    require(timers.selected==selected and timer_view.list.GetFirstSelected()==native_selected,'timer selection preserved')
    require(service.rows[first.timer_id]['state']=='running' and service.rows[second.timer_id]['state']=='running','timers running')
    require(watch.state=='running' and watch.elapsed_ns()==5*10**9,'stopwatch running')
    host.select('stopwatch'); stopwatch_view.tick(); wx.Yield()
    require(wx.Window.FindFocus() is host.choice,'silent update does not move focus')
    # Every borrowed handler remains the very same Python function.
    for panel,dialog,names in (
        (host_ns['AlarmPanel'],alarm_ns['AlarmManager'],('edit','delete','toggle','enable_all','change','refresh')),
        (host_ns['CountdownPanel'],countdown_ns['CountdownDialog'],('edit','delete','preview','refresh','selected','update_buttons')),
        (host_ns['StopwatchPanel'],namespace['StopwatchDialog'],('change_mode','tick','refresh'))):
        for name in names: require(getattr(panel,name) is getattr(dialog,name),'shared handler '+name)
    writes=(watch_repo.writes,timer_repo.writes)
    host.select('world_clock');wx.Yield();world_view=host.views['world_clock']
    require(world_view.automatic.GetValue() and world.policy.enabled,'automatic data updates default enabled')
    native_automatic=native_list_properties(world_view.automatic.GetHandle())
    require(native_automatic['name']==translate('Update data automatically') and native_automatic['role']==44,'automatic checkbox native accessible name/role')
    for enabled in (False,True):
        world_view.automatic.SetValue(enabled)
        event=wx.CommandEvent(wx.EVT_CHECKBOX.typeId,world_view.automatic.GetId());event.SetEventObject(world_view.automatic)
        world_view.automatic.GetEventHandler().ProcessEvent(event);wx.Yield()
        require(world.policy.enabled==enabled,'checkbox applies automatic update setting')
        restored_policy=WorldUpdatePolicy(StopwatchRepository(Path(world_temp.name)/'world_clock_updates.json'))
        require(restored_policy.enabled==enabled,'automatic update setting persists')
    # Reproduce the exact dev13 key exception against NVDA's actual wx module.
    baseline=subprocess.check_output(['git','show','be287576:addon/globalPlugins/awqati/nvda_adapter/world_clock_dialog.py'],cwd=ROOT).decode('utf8')
    old_key=next(n for n in ast.walk(ast.parse(baseline)) if isinstance(n,ast.FunctionDef) and n.name=='key')
    baseline_ns={'wx':wx};exec(compile(ast.Module(body=[old_key],type_ignores=[]),'dev13-key-handler','exec'),baseline_ns)
    try:baseline_ns['key'](world_view,SimpleNamespace(GetKeyCode=lambda:wx.WXK_DOWN,ControlDown=lambda:False,ShiftDown=lambda:False,Skip=lambda:None))
    except AttributeError as error:require('WXK_APPS' in str(error),'exact dev13 key exception')
    else:raise RuntimeError('dev13 keyboard defect not reproduced')
    selected_events=[]
    def selection_probe(event):selected_events.append(event.GetIndex());event.Skip()
    world_view.list.Bind(wx.EVT_LIST_ITEM_SELECTED,selection_probe)
    send=ctypes.WinDLL('user32').SendMessageW
    send.argtypes=(ctypes.c_void_p,ctypes.c_uint,ctypes.c_size_t,ctypes.c_ssize_t);send.restype=ctypes.c_ssize_t
    saved_rows=world.service.rows;focus_passes=0;native_arrow_steps=0
    for rows in ((),saved_rows[:1],saved_rows):
        world.service.rows=rows;world.refresh()
        for repeat in range(10):
            host.choice.SetFocus();wx.Yield();world_view.list.SetFocus();wx.Yield();focus_passes+=1
            for code in (wx.WXK_DOWN,wx.WXK_UP,wx.WXK_TAB,wx.WXK_ESCAPE):
                key=wx.KeyEvent(wx.wxEVT_CHAR_HOOK);key.m_keyCode=code
                world_view.list.GetEventHandler().ProcessEvent(key)
                require(key.GetSkipped(),'normal keyboard event is forwarded')
            if len(rows)>1:
                world_view.list.Select(0);world_view.list.Focus(0);wx.Yield()
                for code,target in ((wx.WXK_DOWN,1),(wx.WXK_DOWN,2),(wx.WXK_UP,1),(wx.WXK_UP,0)):
                    virtual_key=0x28 if code==wx.WXK_DOWN else 0x26
                    send(world_view.list.GetHandle(),0x100,virtual_key,0);send(world_view.list.GetHandle(),0x101,virtual_key,0);wx.Yield()
                    require(world_view.list.GetFirstSelected()==target,'native arrow navigation: '+repr((target,world_view.list.GetFirstSelected())))
                    require(world.selected_id==rows[target].city_id,'selection identity follows native arrows')
                    native_arrow_steps+=1
    world.service.rows=saved_rows;world.refresh();wx.Yield()
    require(len(selected_events)<=100,'bounded selection events during focus and native arrow navigation')
    before=len(selected_events);before_messages=len(messages);before_bytes=world.repository.path.read_bytes()
    for repeat in range(10):
        world_view.list.update_texts();wx.Yield()
        for index in range(3):native_list_properties(world_view.list.GetHandle(),index+1)
    require(len(selected_events)==before and len(messages)==before_messages,'time/MSAA refresh does not reselect or announce')
    require(world.repository.path.read_bytes()==before_bytes,'focus and arrows do not save data')
    original_text=world.text;world.text=lambda city:(_ for _ in ()).throw(RuntimeError('calculation from accessibility callback'))
    try:
        for repeat in range(100):
            for index in range(3):require(world_view.list.GetItemText(index),'cached native row text')
    finally:world.text=original_text
    native_world=native_list_properties(world_view.list.GetHandle())
    require(native_world=={'name':translate('Selected cities'),'role':33},'world-clock selected-list MSAA name and role')
    before_messages=len(messages);before_state=world.repository.path.read_bytes()
    host.choice.SetFocus();world_view.list.Refresh(False);wx.Yield()
    require(wx.Window.FindFocus() is host.choice and len(messages)==before_messages,'world-clock refresh is silent and preserves focus')
    require(world.repository.path.read_bytes()==before_state,'world-clock refresh does not write')
    selected_before=world.selected_id
    for index in range(3):world.announce(index)
    require(world.selected_id==selected_before and world.repository.path.read_bytes()==before_state,'three-city query does not select, save or reorder')
    world_view.list.Select(1);world_view.list.Focus(1);wx.Yield()
    moved=world.service.rows[1].city_id;world_view.move(-1)
    require(world.service.rows[0].city_id==moved and world.selected_id==moved,'move city preserves its identity')
    restored=WorldClockService(world.service.catalog,StopwatchRepository(world.repository.path))
    require(restored.rows==world.service.rows,'city ordering restored from actual file')
    edited_city=world.service.rows[world_view.index()]
    menu_labels=[];original_popup=world_view.list.PopupMenu
    try:
        world_view.list.PopupMenu=lambda menu:menu_labels.extend(item.GetItemLabelText() for item in menu.GetMenuItems())
        world_view.context()
    finally:world_view.list.PopupMenu=original_popup
    require(menu_labels==[translate(text) for text in ('Move up','Move down','Delete city','Edit name')],'native context menu retains actions and adds Edit name')
    names_before=world.service.names(edited_city,language)
    editor_class=world_view_ns['EditCityNameDialog']
    editor=editor_class(frame,world,edited_city)
    require((editor.city_name.GetValue(),editor.country_name.GetValue())==names_before,'edit current field values')
    editor.city_name.SetValue('Cancelled city')
    wx.CallAfter(lambda:editor.EndModal(wx.ID_CANCEL));require(editor.ShowModal()==wx.ID_CANCEL,'cancel name dialog');editor.Destroy()
    require(world.service.names(edited_city,language)==names_before,'cancel preserves names')
    custom_name='أغادير الخاصة' if language=='ar' else 'My city'
    custom_country='بلدي الخاص' if language=='ar' else 'My country'
    editor=editor_class(frame,world,edited_city);editor.city_name.SetValue('  '+custom_name+'  ');editor.country_name.SetValue(custom_country)
    original_box=wx.MessageBox;validation_messages=[]
    try:
        wx.MessageBox=lambda *a,**k:validation_messages.append(a)
        editor.country_name.SetValue(' ');editor.save(None)
        require(validation_messages and editor.city_name.GetValue()=='  '+custom_name+'  ','invalid input preserves dialog data')
    finally:wx.MessageBox=original_box
    editor.country_name.SetValue(custom_country);wx.CallAfter(lambda:editor.save(None));require(editor.ShowModal()==wx.ID_OK,'save edited names');editor.Destroy()
    require(world.service.names(edited_city,language)==(custom_name,custom_country),'trimmed names saved')
    require(custom_name in world.text(edited_city) and custom_country in world.text(edited_city),'custom names in clock query')
    restored=WorldClockService(world.service.catalog,StopwatchRepository(world.repository.path))
    require(restored.names(edited_city,language)==(custom_name,custom_country),'custom names survive actual file reload')
    other_language='en' if language=='ar' else 'ar'
    require(restored.names(edited_city,other_language)==((edited_city.name_ar,edited_city.country_ar) if other_language=='ar' else (edited_city.name_en,edited_city.country_en)),'other language unaffected')
    editor=editor_class(frame,world,edited_city);editor.restore(None)
    require((editor.city_name.GetValue(),editor.country_name.GetValue())==names_before,'restore previews reference names')
    require(world.service.names(edited_city,language)==(custom_name,custom_country),'restore not saved until Save')
    wx.CallAfter(lambda:editor.EndModal(wx.ID_CANCEL));editor.ShowModal();editor.Destroy()
    editor=editor_class(frame,world,edited_city);editor.restore(None)
    wx.CallAfter(lambda:editor.save(None));editor.ShowModal();editor.Destroy()
    require(world.service.names(edited_city,language)==names_before,'restore saves original names')
    city_dialog=world_view_ns['AddCityDialog'](frame,world);city_dialog.Show();wx.Yield()
    require(city_dialog.available.GetCount()==len(world.service.catalog.cities),'all available cities visible without a query')
    native_available=native_list_properties(city_dialog.available.GetHandle())
    require(native_available['name']==translate('Available cities') and native_available['role']==33,'available-city list MSAA name and role')
    for query in ('London','لندن','ابو ظبي'):
        city_dialog.query.SetFocus();city_dialog.query.SetValue(query)
        if city_dialog.pending:city_dialog.pending.Stop()
        city_dialog.filter();wx.Yield()
        require(city_dialog.available.GetCount()>0,'bilingual incremental search '+query)
        require(wx.Window.FindFocus() is city_dialog.query,'search keeps typing focus')
    city_dialog.query.SetValue('Sydney')
    if city_dialog.pending:city_dialog.pending.Stop()
    city_dialog.filter();city_dialog.add(None);wx.Yield()
    require(len(world.service.rows)==4 and city_dialog.IsShown(),'adding a city keeps dialog open')
    city_dialog.add(None);require(len(world.service.rows)==4,'duplicate city rejected')
    city_dialog.Destroy();wx.Yield()
    # Exercise confirmation outcomes through the production handler with a
    # controlled message-box result; no personal NVDA state is involved.
    original_box=wx.MessageBox
    try:
        wx.MessageBox=lambda *a,**k:wx.NO
        old_rows=world.service.rows;world_view.delete();require(world.service.rows==old_rows,'delete refusal preserves cities')
        wx.MessageBox=lambda *a,**k:wx.YES
        world_view.delete();require(len(world.service.rows)==3 and wx.Window.FindFocus() is world_view.list,'confirmed delete restores list focus')
    finally:wx.MessageBox=original_box
    city_times=[world_view.list.GetItemText(i) for i in range(len(world.service.rows))]
    require(all(text and translate('Selected cities') not in text for text in city_times),'native rows expose current times without repeating list name')
    fallback = wx.ListCtrl(frame, style=wx.LC_REPORT | wx.LC_SINGLE_SEL)
    fallback.InsertColumn(0, 'Timer'); fallback.InsertItem(0, 'Fallback timer')
    native_ns['IAccessibleHandler'].accPropServices = None
    native_ns['set_list_name'](fallback, translate('Timers list'))
    require(native_list_properties(fallback.GetHandle()) == {'name':translate('Timers list'), 'role':33}, 'wx.Accessible fallback name and native role')
    live_button=None
    if '--live-update' in sys.argv and language=='ar':
        # Explicit opt-in only: dispatch the real native button and pump wx while
        # the production worker contacts the published public HTTPS channel.
        button=next(child for child in world_view.GetChildren() if isinstance(child,wx.Button) and child.GetLabel()==translate('Update data'))
        def click_and_wait():
            event=wx.CommandEvent(wx.EVT_BUTTON.typeId,button.GetId());event.SetEventObject(button)
            button.GetEventHandler().ProcessEvent(event)
            loop=wx.GUIEventLoop();timed_out=[]
            def done():
                if world.updating:wx.CallLater(25,done)
                else:loop.Exit()
            guard=wx.CallLater(60000,lambda:(timed_out.append(True),loop.Exit()))
            wx.CallAfter(done);loop.Run();guard.Stop()
            require(not timed_out,'live native-button update completed without blocking GUI')
        city=world.service.rows[0];world.service.edit_names(city.city_id,'ar','المدينة المخصصة',city.country_ar)
        user_before=world.repository.path.read_bytes();old_version=world.service.catalog.version
        click_and_wait();require(messages[-1]==translate('World clock data updated.'),'live native-button actual update message')
        require(world.service.catalog.version>old_version,'live native-button activates newer data')
        require(world.repository.path.read_bytes()==user_before and world.service.names(world.service.rows[0],'ar')[0]=='المدينة المخصصة','live button preserves user names and file')
        click_and_wait();require(messages[-1]==translate('World clock data are up to date.'),'live native-button no-update message')
        live_button={'newDataVersion':world.service.catalog.version,'actualUpdate':True,'secondCheckUpToDate':True,'userFileAndNamesPreserved':True,'guiResponsiveWhileWorkerRuns':True}
    frame.Destroy(); wx.Yield()
    require(timers.dialog is None and watch_control.dialog is None,'detached UI references')
    require(watch.state=='running' and service.rows[first.timer_id]['state']=='running','running after settings destruction')
    require(writes==(watch_repo.writes,timer_repo.writes),'no storage writes from switching or closing')
    require(world.dialog is None and world.service.rows,'destroying view preserves world-clock cities')
    world.close();world_temp.cleanup()
    property_services.close()
    return {'language':language,'status':'passed','nativeChoiceLabels':expected,'tools':4,'twoRunningTimers':True,
        'tabAndShiftTab':True,'selectorFocus':True,'selectionPreserved':True,'sharedHandlers':True,
        'noWritesOnSwitchOrClose':True,'runningAfterDestroy':True,'nativeTimerList':native_timer,
        'nativeFirstTimerRow':native_row,'wxAccessibleFallback':True,'worldClockSelectedList':native_world,
        'worldClockAvailableList':native_available,'worldClockSearchAddMoveDeletePersistence':True,
        'worldClockSilentRefresh':True,'worldClockNativeRows':city_times,'nvdaSpeechAndBrailleTested':False,
        'dev13KeyExceptionReproduced':True,'focusEntriesEmptyOneMany':focus_passes,'nativeArrowSteps':native_arrow_steps,
        'selectionEventsBounded':len(selected_events),'accessibilityUsesCachedText':True,
        'editNameSaveCancelRestoreValidationAndLanguageIsolation':True,'automaticUpdateCheckboxNativeAndPersistent':True,'liveNativeButton':live_button}


if __name__=='__main__':
    app=wx.App(False)
    results=[run(language) for language in ('ar','en')]
    result_path=Path(sys.argv[1]) if len(sys.argv)>1 else ROOT/'docs/time_tools_native_wx_results.json'
    result_path.write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n','utf-8')
    print(json.dumps(results,ensure_ascii=True))
