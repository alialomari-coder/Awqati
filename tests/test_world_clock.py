"""World-clock civil-time fixtures and user-data transactions; no live network."""
from copy import deepcopy
from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'addon/globalPlugins'))
from awqati.application.world_clock import WorldClockService, WorldCatalog, describe_city, normalize, arabic_duration
from awqati.domain.world_clock import WorldCity
from awqati.domain import ClockPresentationSettings, TimeRepresentation, HourSystem
from awqati.infrastructure.world_clock import load_data
from awqati.infrastructure.stopwatch import StopwatchRepository
from awqati.infrastructure.windows_local_time import WindowsLocalTimezone

DATA=ROOT/'addon/globalPlugins/awqati/data/world_clock'


class Memory:
    def __init__(self,data=None):self.data=deepcopy(data);self.writes=0;self.fail=False
    def load(self):return deepcopy(self.data)
    def save(self,data):
        if self.fail:raise OSError('disk full')
        self.data=deepcopy(data);self.writes+=1


class WorldDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.catalog,cls.zones,cls.document=load_data(DATA,full=True)

    def test_all_records_are_bilingual_and_identified(self):
        self.assertEqual(1211,len(self.catalog.cities))
        self.assertEqual(248,len({r['country'] for r in self.document['cities']}))
        self.assertEqual(303,len({r['zone'] for r in self.document['cities']}))
        self.assertEqual('2026.6',self.zones.tz_data_version)
        for city in self.catalog.cities.values():
            self.assertTrue(city.city_id.isdecimal())
            self.assertTrue(any('\u0620'<=x<='\u064a' for x in city.name_ar),city.name_en)
            self.assertTrue(city.country_ar)
            self.zones.get_timezone(city.zone)

    def test_required_world_cities_and_all_query_languages(self):
        for term in ('London','New York','Los Angeles','Dubai','Jeddah','Istanbul','Mumbai','Shanghai','Hong Kong','Sydney','Toronto'):
            self.assertTrue(self.catalog.search(term,'en'),term)
        for term in ('لندن','القاهرة','طوكيو','أبو ظبي'):
            self.assertTrue(self.catalog.search(term,'ar'),term)
        self.assertEqual(self.catalog.search('أبو ظبي','ar'),self.catalog.search('ابو ظبي','ar'))
        self.assertEqual(self.catalog.search('london','ar'),self.catalog.search('LONDON','ar'))

    def test_alphabetical_browse_without_query_and_immutable_names(self):
        for language in ('ar','en'):
            cities=self.catalog.search('',language)
            self.assertEqual(len(self.catalog.cities),len(cities))
            keys=[normalize(c.name(language)) for c in cities]
            self.assertEqual(sorted(keys),keys)
        self.assertEqual('ابوظبي',normalize('أَبُوظَبِي'))

    def test_same_country_homonyms_are_disambiguated_in_both_languages(self):
        for lang in ('ar','en'):
            labels=[c.label(lang) for c in self.catalog.cities.values()]
            self.assertEqual(len(labels),len(set(labels)))
        rows=[c for c in self.catalog.cities.values() if c.name_en=='Taizhou']
        self.assertEqual({'Jiangsu','Zhejiang'},{c.admin_en for c in rows})

    def test_corrections_and_small_island_rules_have_representatives(self):
        for key,zone in {'2022773':'Asia/Khandyga','2120048':'Asia/Ust-Nera','4266307':'America/Indiana/Vincennes'}.items():
            self.assertEqual(zone,self.catalog.cities[key].zone)
        used={c.zone for c in self.catalog.cities.values()}
        for zone in ('Pacific/Chatham','Pacific/Marquesas','Pacific/Kanton','Pacific/Kiritimati','Australia/Eucla','Australia/Lord_Howe','America/Noronha','Atlantic/Canary'):
            self.assertIn(zone,used)

    def test_resource_tampering_is_detected_without_network(self):
        with patch('pathlib.Path.read_bytes',autospec=True,side_effect=lambda path:b'bad'):
            with self.assertRaises(ValueError):load_data(DATA)

    def test_reference_backend_matches_all_catalog_zones_at_fixed_dates(self):
        with patch('awqati.infrastructure.timezone_provider._ZoneInfo',None):
            _,fallback,_=load_data(DATA)
            stamps=[datetime(2026,month,15,12,tzinfo=timezone.utc) for month in (1,3,7,11)]
            stamps.append(datetime(2027,1,15,12,tzinfo=timezone.utc))
            for key in {c.zone for c in self.catalog.cities.values()}:
                for stamp in stamps:
                    with self.subTest(zone=key,instant=stamp):
                        expected=stamp.astimezone(self.zones.get_timezone(key))
                        actual=stamp.astimezone(fallback.get_timezone(key))
                        self.assertEqual((expected.replace(tzinfo=None),expected.utcoffset(),expected.fold),
                            (actual.replace(tzinfo=None),actual.utcoffset(),actual.fold))


class WorldStateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.catalog,_,_=load_data(DATA);cls.city=cls.catalog.search('London')[0]

    def test_add_duplicate_order_restart_and_unknown_ids(self):
        repo=Memory();service=WorldClockService(self.catalog,repo)
        first=self.city;second=self.catalog.search('Tokyo')[0]
        self.assertTrue(service.add(first));self.assertTrue(service.add(second));self.assertFalse(service.add(first))
        self.assertEqual(2,repo.writes)
        self.assertEqual(0,service.move(1,-1));self.assertEqual((second,first),service.rows)
        restored=WorldClockService(self.catalog,repo);self.assertEqual(service.rows,restored.rows)
        unknown=WorldCatalog([first],'future')
        restored=WorldClockService(unknown,repo)
        self.assertEqual((second,first),restored.rows)
        self.assertEqual(3,repo.writes)

    def test_save_failure_does_not_change_live_selection_or_previous_file(self):
        repo=Memory();service=WorldClockService(self.catalog,repo);service.add(self.city)
        old=deepcopy(repo.data);repo.fail=True
        with self.assertRaises(OSError):service.delete(0)
        self.assertEqual((self.city,),service.rows);self.assertEqual(old,repo.data)
        with self.assertRaises(OSError):service.add(self.catalog.search('Tokyo')[0])
        self.assertEqual((self.city,),service.rows)

    def test_boundary_moves_and_read_only_queries_do_not_write(self):
        repo=Memory();service=WorldClockService(self.catalog,repo)
        self.assertIsNone(service.first(0));service.add(self.city)
        for index in range(3):service.first(index)
        self.assertEqual(0,service.move(0,-1));self.assertEqual(0,service.move(0,1))
        self.assertEqual(1,repo.writes)

    def test_invalid_and_duplicate_user_records_are_not_overwritten(self):
        for data in ({'schemaVersion':9,'cities':[]},{'schemaVersion':1,'cities':[asdict(self.city),asdict(self.city)]}):
            repo=Memory(data)
            with self.assertRaises(ValueError):WorldClockService(self.catalog,repo)
            self.assertEqual(0,repo.writes);self.assertEqual(data,repo.data)

    def test_real_atomic_persistence_and_invalid_file_preservation(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'cities.json';repo=StopwatchRepository(path)
            service=WorldClockService(self.catalog,repo);service.add(self.city)
            old=path.read_bytes()
            with patch('awqati.infrastructure.stopwatch.os.replace',side_effect=OSError('write failed')):
                with self.assertRaises(OSError):service.delete(0)
            self.assertEqual(old,path.read_bytes());self.assertEqual((self.city,),service.rows)
            path.write_bytes(b'{invalid')
            with self.assertRaises(ValueError):WorldClockService(self.catalog,repo)
            self.assertEqual(b'{invalid',path.read_bytes());self.assertTrue(repo.read_only)


class WorldTimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.catalog,cls.zones,_=load_data(DATA)

    def offset(self,zone,stamp):
        value=datetime.fromisoformat(stamp).replace(tzinfo=timezone.utc)
        return int(value.astimezone(self.zones.get_timezone(zone)).utcoffset().total_seconds()/60)

    def test_fixed_winter_and_summer_reference_table(self):
        for zone,winter,summer in (('Europe/London',0,60),('America/New_York',-300,-240),('Australia/Sydney',660,600),
                ('Asia/Tokyo',540,540),('Asia/Riyadh',180,180),('Africa/Cairo',120,180),
                ('Africa/Casablanca',60,60),('Asia/Kolkata',330,330),('Asia/Kathmandu',345,345)):
            with self.subTest(zone=zone):
                self.assertEqual(winter,self.offset(zone,'2026-01-15T12:00'))
                self.assertEqual(summer,self.offset(zone,'2026-07-15T12:00'))

    def test_dst_transition_instants_and_fold(self):
        cases=(('Europe/London','2026-03-29T00:59',0,'2026-03-29T01:00',60),
            ('Europe/London','2026-10-25T00:59',60,'2026-10-25T01:00',0),
            ('America/New_York','2026-03-08T06:59',-300,'2026-03-08T07:00',-240),
            ('America/New_York','2026-11-01T05:59',-240,'2026-11-01T06:00',-300),
            ('Australia/Sydney','2026-04-04T15:59',660,'2026-04-04T16:00',600),
            ('Australia/Sydney','2026-10-03T15:59',600,'2026-10-03T16:00',660),
            ('Africa/Cairo','2026-04-23T21:59',120,'2026-04-23T22:00',180),
            ('Africa/Cairo','2026-10-29T20:59',180,'2026-10-29T21:00',120),
            ('Africa/Casablanca','2026-02-15T01:59',60,'2026-02-15T02:00',0),
            ('Africa/Casablanca','2026-03-22T01:59',0,'2026-03-22T02:00',60))
        for zone,a,x,b,y in cases:
            with self.subTest(zone=zone,date=a):self.assertEqual(x,self.offset(zone,a));self.assertEqual(y,self.offset(zone,b))

    def test_latest_iana_changes_not_old_dst_predictions(self):
        # IANA 2026d/2026f: Morocco returns to GMT on Sep 20;
        # Manitoba remains -05 and Cuba does not fall back Nov 1, 2026.
        self.assertEqual(60,self.offset('Africa/Casablanca','2026-09-20T00:59'))
        self.assertEqual(0,self.offset('Africa/Casablanca','2026-09-20T01:00'))
        self.assertEqual(-240,self.offset('America/Havana','2026-11-01T06:00'))
        self.assertEqual(-240,self.offset('America/Havana','2027-01-15T12:00'))
        self.assertEqual(-300,self.offset('America/Winnipeg','2026-11-03T12:00'))

    def test_historical_corrections_and_non_effective_identifier_difference(self):
        self.assertEqual(600,self.offset('Asia/Khandyga','2010-01-01T12:00'))
        self.assertEqual(540,self.offset('Asia/Khandyga','2026-01-01T12:00'))
        self.assertEqual(660,self.offset('Asia/Ust-Nera','2010-01-01T12:00'))
        self.assertEqual(600,self.offset('Asia/Ust-Nera','2026-01-01T12:00'))
        self.assertEqual(-360,self.offset('America/Indiana/Vincennes','2007-01-01T12:00'))
        self.assertEqual(-300,self.offset('America/Indiana/Vincennes','2008-01-01T12:00'))
        for stamp in ('2026-01-01T12:00','2026-07-01T12:00'):
            self.assertEqual(self.offset('Africa/Ceuta',stamp),self.offset('Europe/Madrid',stamp))
        self.assertNotEqual(self.offset('Asia/Magadan','2015-07-01T12:00'),self.offset('Asia/Srednekolymsk','2015-07-01T12:00'))

    def test_fractional_differences_day_and_date_change(self):
        options=ClockPresentationSettings(representation=TimeRepresentation.WORDS)
        instant=datetime(2026,11,2,22,30,tzinfo=timezone.utc)
        city=self.catalog.cities[next(c.city_id for c in self.catalog.cities.values() if c.zone=='Asia/Kathmandu')]
        text=describe_city(city,instant,self.zones,timezone(timedelta(hours=3)),'ar',options)
        self.assertIn('الثلاثاء',text);self.assertIn('ساعتين',text);self.assertIn('45 دقيقة',text)
        for local in (timezone(timedelta(hours=5,minutes=45)),timezone(timedelta(hours=8))):
            text=describe_city(city,instant,self.zones,local,'ar',options)
            self.assertIn('موافقة' if local.utcoffset(None)==timedelta(hours=5,minutes=45) else 'متأخرة',text)
        india=replace(city,zone='Asia/Kolkata')
        self.assertIn('30 minutes',describe_city(india,instant,self.zones,timezone(timedelta(hours=3)),'en',options))

    def test_display_respects_clock_preferences_and_time_changes(self):
        city=next(c for c in self.catalog.cities.values() if c.zone=='Europe/London')
        options=ClockPresentationSettings(hour_system=HourSystem.TWENTY_FOUR,speak_seconds=True)
        a=describe_city(city,datetime(2026,1,1,13,2,3,tzinfo=timezone.utc),self.zones,timezone.utc,'en',options)
        b=describe_city(city,datetime(2026,1,1,14,2,3,tzinfo=timezone.utc),self.zones,timezone.utc,'en',options)
        self.assertIn('13',a);self.assertIn('14',b);self.assertNotEqual(a,b)
        self.assertIn('Thursday',a)

    def test_arabic_dual_plural_and_fractional_duration(self):
        self.assertEqual('ساعة واحدة',arabic_duration(60));self.assertEqual('ساعتين',arabic_duration(120))
        self.assertEqual('ثلاث ساعات',arabic_duration(180));self.assertEqual('ساعتين و45 دقيقة',arabic_duration(165))

    def test_trimmed_nvda_runtime_fallback_passes_the_same_independent_time_fixtures(self):
        with patch('awqati.infrastructure.timezone_provider._ZoneInfo',None):
            _,fallback,_=load_data(DATA)
            original=self.zones;self.zones=fallback
            try:
                for name in ('test_fixed_winter_and_summer_reference_table','test_dst_transition_instants_and_fold',
                        'test_latest_iana_changes_not_old_dst_predictions','test_historical_corrections_and_non_effective_identifier_difference',
                        'test_fractional_differences_day_and_date_change'):
                    with self.subTest(fixture=name):getattr(self,name)()
            finally:self.zones=original

    @unittest.skipUnless(sys.platform=='win32','Windows API test')
    def test_windows_reference_uses_current_system_zone_not_prayer_location(self):
        instant=datetime.now(timezone.utc)
        actual=WindowsLocalTimezone()(instant)
        self.assertEqual(instant.astimezone().utcoffset(),actual.utcoffset(None))
        self.assertLess(abs(actual.utcoffset(None).total_seconds()),24*3600)


if __name__=='__main__':unittest.main()
