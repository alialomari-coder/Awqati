"""Immediate production world-clock script and native NVDA repeat engine."""
import ast
import builtins
import gettext
import marshal
from pathlib import Path
import sys
from threading import Event
from types import CodeType,FunctionType,SimpleNamespace
import unittest
import weakref
import zipfile
from time_tools_driver import ADAPTER,ROOT
from test_world_clock import Memory,DATA
from awqati.application.world_clock import WorldClockService
from awqati.infrastructure.world_clock import load_data


def method_class(filename,method,namespace):
    tree=ast.parse((ADAPTER/filename).read_text('utf8'))
    node=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name==method)
    node.decorator_list=[]
    cls=ast.ClassDef(name='Driver',bases=[],keywords=[],body=[node],decorator_list=[])
    exec(compile(ast.fix_missing_locations(ast.Module(body=[cls],type_ignores=[])),filename,'exec'),namespace)
    return namespace['Driver']


class WorldGestureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.catalog,_,_=load_data(DATA)

    def make(self,language='en',cities=3):
        self.calls=[];self.events=[];self.count=0
        translate=gettext.translation('nvda',ROOT/'build/awqati/locale',languages=[language],fallback=True).gettext
        def message(text):self.calls.append(text);self.events.append(('announce',text))
        controller=method_class('world_clock_control.py','announce',{'ui':SimpleNamespace(message=message),'_':translate})()
        controller.service=WorldClockService(self.catalog,Memory());controller.closed=Event()
        for name in ('London','Tokyo','Cairo')[:cities]:controller.service.add(self.catalog.search(name)[0])
        controller.language=lambda:language;controller.text=lambda city:city.name(language)
        controller.selected_id='unrelated-ui-selection'
        fake_speech=SimpleNamespace(cancelSpeech=lambda:self.events.append(('cancel',None)))
        def import_boundary(name,*args,**kwargs):
            return fake_speech if name=='speech' else builtins.__import__(name,*args,**kwargs)
        self.native=SimpleNamespace(getLastScriptRepeatCount=lambda:self.count)
        driver=method_class('plugin.py','script_worldClock',{'scriptHandler':self.native,
            '__builtins__':dict(vars(builtins),__import__=import_boundary)})()
        driver._world_clock=controller;driver._terminated=False
        return driver,controller

    def press(self,driver,times):
        for count in range(times):
            self.count=count;before=len(self.calls);driver.script_worldClock(None)
            self.assertEqual(before+1,len(self.calls))
        self.assertEqual(['announce']*times,[kind for kind,_ in self.events])

    def test_single_double_triple_only_announce_the_requested_city_in_both_languages(self):
        for language in ('ar','en'):
            for presses in (1,2,3):
                with self.subTest(language=language,presses=presses):
                    driver,control=self.make(language)
                    before=control.service.repository.writes;rows=control.service.rows
                    self.press(driver,presses)
                    self.assertEqual([city.name(language) for city in rows[:presses]],self.calls)
                    self.assertEqual(rows,control.service.rows)
                    self.assertEqual(before,control.service.repository.writes)
                    self.assertEqual('unrelated-ui-selection',control.selected_id)
                    self.assertFalse(hasattr(driver,'_world_presses'))

    def test_empty_one_and_two_city_lists_have_localized_messages(self):
        for language in ('ar','en'):
            for count,presses,message in ((0,1,'لم تُضف أي مدينة بعد' if language=='ar' else 'No city has been added yet.'),
                    (1,2,'لا توجد مدينة ثانية' if language=='ar' else 'There is no second city.'),
                    (2,3,'لا توجد مدينة ثالثة' if language=='ar' else 'There is no third city.')):
                driver,_=self.make(language,count);self.press(driver,presses);self.assertEqual(message,self.calls[-1])

    def test_reordered_cities_are_queried_in_user_order(self):
        driver,control=self.make();control.service.move(2,-1);control.service.move(1,-1)
        self.press(driver,1);self.assertEqual([control.service.rows[0].name_en],self.calls)

    def test_shutdown_and_fourth_press_have_no_extra_speech_or_pending_actions(self):
        driver,_=self.make();driver._terminated=True;driver.script_worldClock(None)
        self.assertEqual([],self.calls);self.assertEqual([],self.events)
        driver,control=self.make();self.press(driver,4)
        self.assertEqual([city.name_en for city in control.service.rows]+[control.service.rows[-1].name_en],self.calls)

    def test_script_contains_no_scheduler_or_timeout_and_other_scripts_are_unchanged(self):
        import subprocess
        current=ast.parse((ADAPTER/'plugin.py').read_text('utf8'))
        from multipress_history import restore_dev17_plugin
        restored=restore_dev17_plugin(current)
        previous=ast.parse(subprocess.check_output(['git','show','7de23726:addon/globalPlugins/awqati/nvda_adapter/plugin.py'],cwd=ROOT).decode('utf8'))
        scripts=lambda tree:{n.name:ast.dump(n) for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name.startswith('script_') and n.name!='script_worldClock'}
        self.assertEqual(scripts(previous),scripts(restored))
        script=next(n for n in ast.walk(current) if isinstance(n,ast.FunctionDef) and n.name=='script_worldClock')
        names={n.attr for n in ast.walk(script) if isinstance(n,ast.Attribute)}
        self.assertTrue({'getLastScriptRepeatCount','announce'}<=names)
        self.assertFalse({'cancelSpeech','CallLater','schedule','submit','multiPressTimeout'}&names)

    def test_new_gesture_is_unique_and_all_previous_gestures_are_preserved(self):
        tree=ast.parse((ADAPTER/'plugin.py').read_text('utf8'))
        gestures=[]
        for node in ast.walk(tree):
            if isinstance(node,ast.keyword) and node.arg=='gesture' and isinstance(node.value,ast.Constant):
                gestures.append(node.value.value.lower().replace('ctrl','control'))
        self.assertEqual(1,gestures.count('kb:nvda+control+f12'))
        self.assertEqual(len(gestures),len(set(gestures)))

    @unittest.skipUnless(Path(r'C:\Program Files\NVDA\library.zip').exists() and sys.version_info[:2]==(3,13),
        'Installed native NVDA CPython 3.13 script engine')
    def test_native_nvda_engine_reaches_production_world_clock_script(self):
        with zipfile.ZipFile(r'C:\Program Files\NVDA\library.zip') as archive:
            code=marshal.loads(archive.read('scriptHandler.pyc')[16:])
        functions={c.co_name:c for c in code.co_consts if isinstance(c,CodeType)}
        for presses in (1,2,3):
            driver,control=self.make();now=[100.0];errors=[]
            ns=dict(_lastScriptRef=None,_isScriptRunning=False,_lastScriptTime=0,_lastScriptCount=0,
                time=SimpleNamespace(time=lambda:now[0]),weakref=weakref,
                config=SimpleNamespace(conf={'keyboard':{'multiPressTimeout':500}}),
                willSayAllResume=lambda gesture:False,log=SimpleNamespace(exception=lambda *a:errors.append(a)))
            execute=FunctionType(functions['executeScript'],ns);repeat=FunctionType(functions['getLastScriptRepeatCount'],ns)
            self.native.getLastScriptRepeatCount=repeat
            for index in range(presses):
                now[0]+=.1;execute(driver.script_worldClock,SimpleNamespace(displayName='World clock'))
                self.assertEqual(index+1,len(self.calls))
                self.assertEqual(control.service.rows[index].name_en,self.calls[-1])
            self.assertFalse(errors)
            self.assertEqual(['announce']*presses,[kind for kind,_ in self.events])
            # A new native sequence after its existing timeout starts at zero.
            now[0]+=1;execute(driver.script_worldClock,SimpleNamespace(displayName='World clock'))
            self.assertEqual(control.service.rows[0].name_en,self.calls[-1]);self.assertEqual(presses+1,len(self.calls))


if __name__=='__main__':unittest.main()
