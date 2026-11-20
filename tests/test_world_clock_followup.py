"""Regression for dev13 keyboard exceptions and language-specific display names."""
from dataclasses import asdict,replace
from datetime import datetime,timezone
from threading import Event
from types import SimpleNamespace
import unittest
from unittest.mock import Mock
from time_tools_driver import definitions
from test_world_clock import Memory,DATA
import test_world_clock_gestures as gesture_driver
from awqati.application.world_clock import WorldClockService,WorldCatalog,describe_city,validate_display_name
from awqati.infrastructure.world_clock import load_data
from awqati.domain import ClockPresentationSettings


class DisplayNameTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.catalog,cls.zones,_=load_data(DATA)

    def setUp(self):
        self.repo=Memory();self.service=WorldClockService(self.catalog,self.repo)
        self.city=self.catalog.search('Agadir')[0];self.service.add(self.city)

    def edit(self,city=None,country=None,language='ar'):
        names=self.service.names(self.city,language)
        self.service.edit_names(self.city.city_id,language,city if city is not None else names[0],country if country is not None else names[1])

    def test_city_only_country_only_and_both(self):
        self.edit(city='أغادير');self.assertEqual(('أغادير',self.city.country_ar),self.service.names(self.city,'ar'))
        self.edit(country='المغرب المخصص');self.assertEqual(('أغادير','المغرب المخصص'),self.service.names(self.city,'ar'))
        self.edit(city='اسم آخر',country='بلد آخر');self.assertEqual(('اسم آخر','بلد آخر'),self.service.names(self.city,'ar'))
        self.assertEqual((self.city.name_en,self.city.country_en),self.service.names(self.city,'en'))

    def test_independent_language_overrides_and_restart(self):
        self.edit(city='أغادير');self.edit(city='My Agadir',language='en')
        restored=WorldClockService(self.catalog,self.repo)
        self.assertEqual('أغادير',restored.names(self.city,'ar')[0]);self.assertEqual('My Agadir',restored.names(self.city,'en')[0])
        self.assertEqual(self.city,restored.rows[0]);self.assertEqual(asdict(self.city),self.repo.data['cities'][0])

    def test_no_reference_data_mutation_or_timezone_changes(self):
        original=asdict(self.city);self.edit(city='اسم مختلف',country='دولة مخصصة')
        self.assertEqual(original,asdict(self.catalog.cities[self.city.city_id]));self.assertEqual(self.city,self.service.rows[0])
        for stamp in ('2026-01-15T12:00','2026-07-15T12:00','2026-09-20T01:00'):
            instant=datetime.fromisoformat(stamp).replace(tzinfo=timezone.utc)
            before=describe_city(self.city,instant,self.zones,timezone.utc,'ar',ClockPresentationSettings())
            after=describe_city(self.city,instant,self.zones,timezone.utc,'ar',ClockPresentationSettings(),self.service.display(self.city,'ar'))
            self.assertEqual(before.split('، الساعة ',1)[1],after.split('، الساعة ',1)[1]);self.assertIn('دولة مخصصة',after)

    def test_trim_limit_controls_and_empty_fields(self):
        self.edit(city='  أغادير  ');self.assertEqual('أغادير',self.service.names(self.city,'ar')[0])
        self.assertEqual('س'*160,validate_display_name('س'*160))
        for value in ('','   ','س'*161,'اسم\nثان','\tاسم','اسم\x00','اسم\u202e','اسم\u2028ثان'):
            for field in ('city','country'):
                with self.subTest(value=value,field=field):
                    old=self.repo.data;writes=self.repo.writes
                    with self.assertRaises(ValueError):self.edit(**{field:value})
                    self.assertEqual(old,self.repo.data);self.assertEqual(writes,self.repo.writes)

    def test_failed_write_preserves_names_and_rows(self):
        self.edit(city='أغادير');old=self.repo.data;self.repo.fail=True
        with self.assertRaises(OSError):self.edit(country='بلد آخر')
        self.assertEqual(old,self.repo.data);self.assertEqual(('أغادير',self.city.country_ar),self.service.names(self.city,'ar'))

    def test_restore_removes_current_language_only(self):
        self.edit(city='أغادير');self.edit(city='My Agadir',language='en')
        self.edit(city=self.city.name_ar,country=self.city.country_ar)
        self.assertNotIn('ar',self.repo.data['displayNames'][self.city.city_id]);self.assertEqual('My Agadir',self.service.names(self.city,'en')[0])

    def test_reorder_add_delete_and_unknown_city_preserve_other_customizations(self):
        self.edit(city='أغادير');other=self.catalog.search('Tokyo')[0];self.service.add(other);self.service.move(0,1)
        restored=WorldClockService(WorldCatalog([other],'new'),self.repo)
        self.assertEqual('أغادير',restored.names(restored.rows[1],'ar')[0]);self.assertEqual(self.city,restored.rows[1])
        self.service.delete(0);self.assertEqual('أغادير',self.service.names(self.city,'ar')[0])
        self.service.delete(0);self.assertNotIn('displayNames',self.repo.data)

    def test_updated_reference_retains_custom_and_updates_noncustom_field(self):
        self.edit(city='أغادير')
        updated=replace(self.city,name_ar='اسم مرجعي أحدث',country_ar='بلد مرجعي أحدث')
        restored=WorldClockService(WorldCatalog([updated],'new'),self.repo)
        self.assertEqual(('أغادير','بلد مرجعي أحدث'),restored.names(updated,'ar'))

    def test_real_controller_reload_preserves_overrides_and_shortcut_text(self):
        self.edit(city='أغادير',country='بلد مخصص')
        ns={'WindowsLocalTimezone':lambda:lambda instant:timezone.utc,'ClockType':__import__('awqati.domain',fromlist=['ClockType']).ClockType,
            'datetime':datetime,'timezone':timezone,'describe_city':describe_city}
        definitions('world_clock_control.py',ns,{'WorldClockControl'})
        control=ns['WorldClockControl'].__new__(ns['WorldClockControl']);control.service=self.service;control.updater=object()
        updated=replace(self.city,name_ar='اسم جديد')
        control.reload((WorldCatalog([updated],'new'),self.zones,{},{}))
        control.language=lambda:'ar'
        control.runtime=SimpleNamespace(settings=SimpleNamespace(runtime_settings=SimpleNamespace(clock=SimpleNamespace(presentations={ns['ClockType'].ZAWALI:ClockPresentationSettings()}))))
        text=control.text(control.service.rows[0]);self.assertIn('أغادير',text);self.assertIn('بلد مخصص',text)
        self.assertEqual(self.city.zone,control.service.rows[0].zone)

    def test_three_press_production_dispatch_uses_custom_third_name(self):
        # Reuse the immediate production-script driver, with real formatter.
        driver_test=gesture_driver.WorldGestureTests();driver_test.catalog=self.catalog;driver,control=driver_test.make()
        city=control.service.rows[2];control.service.edit_names(city.city_id,'en','My third city','My country')
        control.text=lambda city:describe_city(city,datetime(2026,7,1,12,tzinfo=timezone.utc),self.zones,timezone.utc,'en',ClockPresentationSettings(),control.service.display(city,'en'))
        driver_test.press(driver,3)
        self.assertEqual(3,len(driver_test.calls));self.assertIn('My third city (My country)',driver_test.calls[-1])


class KeyboardAndCacheTests(unittest.TestCase):
    def test_keyboard_context_menu_can_translate_without_local_underscore_shadowing(self):
        menus=[]
        class Menu:
            def __init__(self):self.labels=[];self.enabled=[];menus.append(self)
            def Append(self,identity,label):
                self.labels.append(label);return SimpleNamespace(Enable=self.enabled.append)
            def Bind(self,*args):pass
            def Destroy(self):self.destroyed=True
        wx=SimpleNamespace(Panel=object,Dialog=object,ListCtrl=object,Menu=Menu,ID_ANY=-1,EVT_MENU=1)
        ns={'wx':wx,'_':lambda text:text};definitions('world_clock_dialog.py',ns)
        panel=ns['WorldClockPanel'].__new__(ns['WorldClockPanel']);panel.control=SimpleNamespace(service=SimpleNamespace(rows=[1,2,3]))
        panel.index=lambda:1;panel.list=Mock();panel.move=Mock();panel.delete=Mock();panel.edit_name=Mock()
        panel.context()
        self.assertEqual(['Move up','Move down','Delete city','Edit name'],menus[0].labels)
        self.assertEqual([True]*4,menus[0].enabled);self.assertTrue(menus[0].destroyed);panel.list.SetFocus.assert_called_once()

    def test_native_key_constants_forward_normal_keys_for_empty_and_populated_lists(self):
        wx=SimpleNamespace(WXK_UP=315,WXK_DOWN=317,WXK_DELETE=127,WXK_WINDOWS_MENU=395,WXK_F10=349,Panel=object,Dialog=object,ListCtrl=object)
        ns={'wx':wx};definitions('world_clock_dialog.py',ns)
        panel=ns['WorldClockPanel'].__new__(ns['WorldClockPanel'])
        panel.move=Mock();panel.delete=Mock();panel.context=Mock()
        for rows in ((),(1,),(1,2,3)):
            panel.control=SimpleNamespace(service=SimpleNamespace(rows=rows))
            for key in (315,317,9,27,65):
                event=SimpleNamespace(GetKeyCode=lambda:key,ControlDown=lambda:False,ShiftDown=lambda:False,Skip=Mock())
                panel.key(event);event.Skip.assert_called_once()
        panel.context.assert_not_called();panel.move.assert_not_called()
        for key,ctrl,shift,method in ((395,False,False,panel.context),(349,False,True,panel.context),(315,True,False,panel.move),(317,True,False,panel.move),(127,False,False,panel.delete)):
            before=method.call_count;event=SimpleNamespace(GetKeyCode=lambda:key,ControlDown=lambda:ctrl,ShiftDown=lambda:shift,Skip=Mock())
            panel.key(event);self.assertEqual(before+1,method.call_count);event.Skip.assert_not_called()

    def test_accessibility_text_callbacks_are_pure_cached_reads(self):
        ns={'wx':SimpleNamespace(Panel=object,Dialog=object,ListCtrl=object)};definitions('world_clock_dialog.py',ns)
        listing=ns['SelectedCityList'].__new__(ns['SelectedCityList']);listing.texts=('one','two','three');listing.control=Mock()
        for _ in range(1000):
            for i in (-1,0,1,2,3):self.assertEqual(('one','two','three')[i] if 0<=i<3 else '',listing.OnGetItemText(i,0))
        self.assertEqual([],listing.control.mock_calls)

    def test_selection_event_never_refreshes_selects_saves_or_speaks(self):
        ns={'wx':SimpleNamespace(Panel=object,Dialog=object,ListCtrl=object)};definitions('world_clock_dialog.py',ns)
        panel=ns['WorldClockPanel'].__new__(ns['WorldClockPanel']);panel.control=SimpleNamespace(service=SimpleNamespace(rows=[SimpleNamespace(city_id=str(i)) for i in range(3)]))
        panel.refresh=Mock();panel.list=Mock()
        for _ in range(20):
            for index in range(3):
                event=SimpleNamespace(GetIndex=lambda:index,Skip=Mock());panel.selected(event)
                self.assertEqual(str(index),panel.control.selected_id);event.Skip.assert_called_once()
        panel.refresh.assert_not_called();self.assertEqual([],panel.list.mock_calls)


if __name__=='__main__':unittest.main()
