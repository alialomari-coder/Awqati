"""Regression tests for timing semantics, localized places and native COM lifecycle."""
import ast
import ctypes
import gzip
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'addon/globalPlugins'), str(ROOT/'.build-deps'), str(ROOT)]
from awqati.domain import MorningReference, EveningReference, FridayReference, LocationDetectionFailure
from awqati.application import LocationDetectionError
from awqati.infrastructure import BundledLocationRepository, WindowsLocationAdapter
from awqati.infrastructure.windows_location import _status_failure, _LIVE_SINKS
from awqati.nvda_adapter.location_labels import city_name, subdivisions
from babel.messages.pofile import read_po
from tools.build_locations import add_alternate_names, _ordered_names
import tempfile

class TimingLabelsTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  with (ROOT/'addon/locale/ar/LC_MESSAGES/nvda.po').open('rb') as f: cls.catalog=read_po(f)
  cls.tree=ast.parse((ROOT/'addon/globalPlugins/awqati/nvda_adapter/settings_panel.py').read_text('utf-8'))
 def test_no_ambiguous_or_inconsistent_arabic_terms(self):
  values='\n'.join(str(m.string) for m in self.catalog)
  for text in ('مدة التنبيه قبل دخول الوقت','مدة التنبيه بعد دخول الوقت','مدة أذكار الصباح','مدة أذكار المساء','مدة تذكير ساعة الجمعة','الأذكار المتكررة','التذكير المتكرر'):
   self.assertNotIn(text, values)
  self.assertEqual(self.catalog['Enable recurring Dhikr reminder'].string,'تفعيل الأذكار الدورية')
 def test_each_reference_updates_native_label_and_accessible_name_without_focus_or_rebuild(self):
  ns={'set_spin_name':lambda control,name:control.SetName(name),'N_':lambda s:s,'_':lambda s:self.catalog[s].string,'MorningReference':MorningReference,'EveningReference':EveningReference,'FridayReference':FridayReference,'STANDARD_ALERT_ACTIONS':(), 'AlertOutputEditor':Mock()}
  assignment=next(n for n in self.tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='TIMED_ALERT_LABELS' for t in n.targets))
  method=next(n for c in self.tree.body if isinstance(c,ast.ClassDef) for n in c.body if isinstance(n,ast.FunctionDef) and n.name=='_build_timed_adhkar')
  exec(compile(ast.Module(body=[assignment,method],type_ignores=[]),'timed-labels','exec'),ns)
  for key,enum in (('morning',MorningReference),('evening',EveningReference),('friday',FridayReference)):
   reference=Mock();minutes=Mock();minutes.awqati_label=Mock();bindings={}
   reference.Bind.side_effect=lambda event,fn:bindings.update(change=fn)
   ns.update(_choice=Mock(return_value=reference),_spin=Mock(return_value=minutes),wx=SimpleNamespace(EVT_CHOICE=1,EVT_SPINCTRL=2))
   owner=Mock();panel=Mock();value=SimpleNamespace(reference=list(enum)[0],minutes=15,alert=object())
   ns['_build_timed_adhkar'](owner,panel,Mock(),key,value)
   for i,item in enumerate(enum):
    reference.GetSelection.return_value=i
    bindings['change'](Mock())
    label,name=ns['TIMED_ALERT_LABELS'][item.value]
    self.assertEqual(value.reference,item)
    minutes.awqati_label.SetLabel.assert_called_with(self.catalog[label].string)
    minutes.SetName.assert_called_with(self.catalog[name].string)
    self.assertIn('بالدقائق', self.catalog[name].string)
    self.assertNotIn('مدة', self.catalog[label].string)
    self.assertEqual(value.minutes,15)
   reference.SetFocus.assert_not_called();minutes.SetFocus.assert_not_called()
   owner._render_section.assert_not_called();ns['_spin'].assert_called_once()
   self.assertEqual(ns['AlertOutputEditor'].call_args.args[2],'Alert action:')
 def test_prayer_visible_labels_and_accessible_units(self):
  for direction,arabic in (('before','قبل'),('after','بعد')):
   self.assertEqual(self.catalog[f'Alert {direction} the event:'].string,f'التنبيه {arabic} دخول الوقت بـ:')
   self.assertEqual(self.catalog[f'Alert {direction} the event, minutes'].string,f'التنبيه {arabic} دخول الوقت بـ، بالدقائق')

class PlaceDisplayTests(unittest.TestCase):
 def setUp(self): self.repo=BundledLocationRepository()
 def test_global_city_samples_use_bundled_source_names(self):
  samples=[('SA','108410'),('SA','110336'),('SA','104515'),('EG','360630'),('GB','2643743'),('FR','2988507'),('US','5128581'),('TR','745044'),('RU','524901'),('JP','1850147')]
  for cc,identity in samples:
   with self.subTest(country=cc,identity=identity):
    match=self.repo.get(cc,identity);self.assertIsNotNone(match)
    records=json.loads(gzip.decompress((ROOT/f'addon/globalPlugins/awqati/data/locations/countries/{cc}.json.gz').read_bytes()))['cities']
    record=next(r for r in records if r['i']==identity)
    self.assertTrue(record['a']);self.assertEqual(city_name(match,'ar'),record['a'][0])
    self.assertEqual(city_name(match,'en'),record['e'][0] if record['e'] else record['n'])
    self.assertEqual(match.location.location_id,identity)
    for query in (city_name(match,'ar'),record['n']):
     self.assertIn(identity,[m.location.location_id for m in self.repo.search(cc,query,40)])
 def test_fallback_and_admin_display_are_source_based(self):
  match=self.repo.get('GB','2643743')
  self.assertTrue(match.arabic_admin1_names)
  self.assertIn(match.arabic_admin1_names[0],subdivisions(match,'ar'))
  from dataclasses import replace
  fallback=replace(match,arabic_names=(),arabic_admin1_names=(),arabic_admin2_names=())
  self.assertEqual(city_name(fallback,'ar'),match.location.name)
  self.assertEqual(subdivisions(fallback,'ar'),match.subdivisions)
 def test_coverage_matches_every_country(self):
  root=ROOT/'addon/globalPlugins/awqati/data/locations'
  meta=json.loads((root/'metadata.json').read_text('utf-8'));total=named=0
  for entry in meta['countries']:
   records=json.loads(gzip.decompress((root/entry['file']).read_bytes()))['cities']
   total+=len(records);named+=sum(bool(r['a']) for r in records)
  self.assertEqual(meta['arabicCoverage'],{'cityCount':total,'namedCityCount':named,'missingCityCount':total-named})
  self.assertGreater(total-named,0)
 def test_build_rejects_historic_expired_and_non_arabic_names(self):
  rows=[('1','ar','قديم','1','','','1','',''),('2','ar','منتهي','1','','','','','1900'),('3','ar','English','1','','','','',''),('4','ar','اسم آخر','','','','','',''),('5','ar','اسم معتمد','1','','','','','')]
  with tempfile.TemporaryDirectory() as temp:
   path=Path(temp)/'alternateNamesV2.txt'
   path.write_text(''.join('\t'.join((i,'123',lang,name,*flags))+'\n' for i,lang,name,*flags in rows),encoding='utf-8')
   cities={'123':{'ar':{},'en':{}}};add_alternate_names(path,cities)
  self.assertEqual(_ordered_names(cities['123']['ar']),['اسم معتمد','اسم آخر'])

@unittest.skipUnless(os.name=='nt','Native COM ABI is Windows-only')
class NativeLocationContractTests(unittest.TestCase):
 def native(self,report=True,status=4,permission=0,registration=0,null=False):
  calls=[];callbacks=[];sink=[None]
  def cb(types,fn):
   callback=ctypes.WINFUNCTYPE(ctypes.c_long,ctypes.c_void_p,*types)(fn);callbacks.append(callback);return ctypes.cast(callback,ctypes.c_void_p).value
  P=ctypes.c_void_p;PP=ctypes.POINTER(P)
  report_table=(P*8)()
  report_pointer=P(ctypes.addressof(report_table))
  report_address=ctypes.addressof(report_pointer)
  def qi(this,iid,out):out[0]=report_address;return 0
  report_table[0]=cb((P,PP),qi)
  report_table[2]=cb((),lambda this:calls.append('report_release') or 0)
  def coordinate(this,out):out[0]=1.0;return 0
  report_table[6]=cb((ctypes.POINTER(ctypes.c_double),),coordinate)
  report_table[7]=cb((ctypes.POINTER(ctypes.c_double),),coordinate)
  table=(P*12)();pointer=P(ctypes.addressof(table));address=ctypes.addressof(pointer)
  def sink_method(index,*types):
   v=ctypes.cast(sink[0],ctypes.POINTER(ctypes.POINTER(P))).contents
   return ctypes.WINFUNCTYPE(ctypes.c_long,P,*types)(v[index])
  def register(this,event,iid,interval):
   calls.append('register');sink[0]=event
   if registration:return registration
   sink_method(1)(event)
   if report:sink_method(3,P,P)(event,iid,None if null else report_address)
   return 0
  def unregister(this,iid):calls.append('unregister');sink_method(2)(sink[0]);return 0
  def get_status(this,iid,out):calls.append('status');out[0]=status;return 0
  table[2]=cb((),lambda this:calls.append('location_release') or 0)
  table[3]=cb((P,P,ctypes.c_ulong),register)
  table[4]=cb((P,),unregister)
  table[6]=cb((P,ctypes.POINTER(ctypes.c_int)),get_status)
  table[11]=cb((P,P,ctypes.c_ulong,ctypes.c_int),lambda *args:calls.append('permission') or permission)
  def create(clsid,outer,context,iid,out):ctypes.cast(out,PP)[0]=address;return 0
  ole=SimpleNamespace(CoInitializeEx=Mock(return_value=0),CoCreateInstance=Mock(side_effect=create),CoUninitialize=Mock())
  adapter=WindowsLocationAdapter(timeout_seconds=.001)
  with patch.object(ctypes,'WinDLL',return_value=ole):
   try:value=adapter.get_coordinates();failure=None
   except LocationDetectionError as error:value=None;failure=error.failure
  self.assertFalse(_LIVE_SINKS)
  ole.CoUninitialize.assert_called_once()
  self.assertEqual(calls[-1],'location_release')
  self.assertFalse({'latitude','longitude','coordinates'} & set(adapter.last_diagnostics))
  return value,failure,calls,adapter.last_diagnostics
 def test_registration_report_and_cleanup(self):
  value,failure,calls,diag=self.native()
  self.assertIsNone(failure);self.assertEqual(value.latitude,1.0)
  self.assertEqual(calls,['permission','register','report_release','unregister','location_release'])
  self.assertTrue(diag['report_received'])
 def test_status_classification_after_wait_and_cleanup(self):
  for status in range(5):
   with self.subTest(status=status):
    value,failure,calls,diag=self.native(report=False,status=status)
    self.assertIsNone(value);self.assertEqual(failure,_status_failure(status))
    self.assertIn('unregister',calls);self.assertEqual(diag['report_status'],status)
 def test_permission_hresult_denial_does_not_register(self):
  _,failure,calls,_=self.native(permission=-2147024891)
  self.assertEqual(failure,LocationDetectionFailure.DENIED);self.assertNotIn('register',calls)
 def test_registration_failure_releases_com_without_unregister(self):
  _,failure,calls,_=self.native(registration=-2147467259)
  self.assertEqual(failure,LocationDetectionFailure.API_ERROR);self.assertNotIn('unregister',calls)
 def test_bad_report_is_contained_and_cleanup_runs(self):
  _,failure,calls,_=self.native(null=True)
  self.assertEqual(failure,LocationDetectionFailure.API_ERROR);self.assertIn('unregister',calls)

if __name__=='__main__':unittest.main()

class NativeAccessibleNameTests(unittest.TestCase):
 def namespace(self, services):
  tree=ast.parse((ROOT/'addon/globalPlugins/awqati/nvda_adapter/native_accessibility.py').read_text('utf-8'))
  function=next(n for n in tree.body if isinstance(n,ast.FunctionDef))
  send=Mock(return_value=102)
  ns=dict(IAccessibleHandler=SimpleNamespace(accPropServices=services),oleacc=SimpleNamespace(PROPID_ACC_NAME=ctypes.c_int(1)),wx=SimpleNamespace(EVT_WINDOW_DESTROY=99),WinDLL=Mock(return_value=SimpleNamespace(SendMessageW=send)),c_void_p=ctypes.c_void_p,c_uint=ctypes.c_uint,c_size_t=ctypes.c_size_t,c_ssize_t=ctypes.c_ssize_t,byref=ctypes.byref)
  exec(compile(ast.Module(body=[function],type_ignores=[]),'native-name','exec'),ns)
  control=SimpleNamespace(SetName=Mock(),GetHandle=Mock(return_value=101),Bind=Mock(),awqati_label=Mock())
  return ns,control
 def test_dynamic_name_reaches_native_spin_and_edit_without_rebinding(self):
  services=Mock();ns,control=self.namespace(services)
  ns['set_spin_name'](control,'before sunrise, minutes');ns['set_spin_name'](control,'after sunrise, minutes')
  self.assertEqual(control._awqati_name_handles,(101,102));control.Bind.assert_called_once()
  self.assertEqual([(c.args[0],c.args[-1]) for c in services.SetHwndPropStr.call_args_list],[(101,'before sunrise, minutes'),(102,'before sunrise, minutes'),(101,'after sunrise, minutes'),(102,'after sunrise, minutes')])
 def test_annotations_clear_only_when_own_control_is_destroyed(self):
  services=Mock();ns,control=self.namespace(services);ns['set_spin_name'](control,'minutes')
  handler=control.Bind.call_args.args[1];event=Mock();event.GetEventObject.return_value=object();handler(event);services.ClearHwndProps.assert_not_called()
  event.GetEventObject.return_value=control;handler(event)
  self.assertEqual([c.args[0] for c in services.ClearHwndProps.call_args_list],[101,102]);self.assertEqual(event.Skip.call_count,2)
 def test_unavailable_annotation_keeps_unit_in_native_label(self):
  ns,control=self.namespace(None);ns['set_spin_name'](control,'before sunrise, minutes');control.awqati_label.SetLabel.assert_called_once_with('before sunrise, minutes:');control.Bind.assert_not_called()
