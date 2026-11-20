"""The audit must reject known geographic errors and avoid homonym matches."""
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
from audit_world_clock_sources import iana_coordinates, distance_km, exemplar_conflicts, build


class Wheel:
    def read(self, name):
        zone = name.removeprefix('tzdata/zoneinfo/')
        return (ROOT/'addon/globalPlugins/awqati/data/timezones/zoneinfo'/zone).read_bytes()


def city(name='Khandyga', zone='Asia/Vladivostok', latitude='62.65302', longitude='135.56649'):
    return {'id':'2022773','en':name,'native':name,'country':'RU','zone':zone,'lat':latitude,'lon':longitude}


class SourceGateTests(unittest.TestCase):
    def test_iana_coordinates_with_seconds_and_negative_values(self):
        lat,lon=iana_coordinates('+623923+1353314')
        self.assertAlmostEqual(62+39/60+23/3600,lat)
        self.assertAlmostEqual(135+33/60+14/3600,lon)
        self.assertEqual((-31.95,115.85),iana_coordinates('-3157+11551'))

    def test_coordinates_reject_incomplete_value(self):
        with self.assertRaises(ValueError): iana_coordinates('+6239+135')

    def test_distance_near_and_far(self):
        self.assertEqual(0,distance_km((0,0),(0,0)))
        self.assertGreater(distance_km((-41.57,147.17),(-31.95,115.85)),2000)

    def test_real_offset_conflict_detected(self):
        rows=exemplar_conflicts({'1':city()},[['RU','+623923+1353314','Asia/Khandyga']],lambda x:x,Wheel())
        self.assertEqual(1,len(rows))
        self.assertEqual(60,rows[0]['differenceMinutes'])
        self.assertLess(rows[0]['distanceFromIanaPointKm'],1)

    def test_homonym_in_another_region_is_not_a_conflict(self):
        self.assertEqual([],exemplar_conflicts({'1':city(latitude='50',longitude='100')},
            [['RU','+623923+1353314','Asia/Khandyga']],lambda x:x,Wheel()))

    def test_alias_equivalence_is_not_a_conflict(self):
        self.assertEqual([],exemplar_conflicts({'1':city(zone='Alias')},
            [['RU','+623923+1353314','Asia/Khandyga']],lambda x:'Asia/Khandyga',Wheel()))

    def test_different_country_is_not_matched(self):
        self.assertEqual([],exemplar_conflicts({'1':city()},
            [['US','+623923+1353314','Asia/Khandyga']],lambda x:x,Wheel()))

    def test_original_source_audit_is_rejected_and_later_corrections_are_reviewed(self):
        report=json.loads((ROOT/'docs/world_clock_source_audit.json').read_text('utf8'))
        self.assertFalse(report['runtimeApproved'])
        self.assertEqual('REJECTED_TIMEZONE_ASSOCIATIONS',report['status'])
        bad=[c for c in report['geographicZoneConflicts'] if c['differenceMinutes']]
        self.assertEqual({'2022773','2120048','4266307'},{c['geonameId'] for c in bad})
        reviewed=json.loads((ROOT/'docs/world_clock_data_review.json').read_text('utf8'))
        self.assertTrue(reviewed['approved'])
        self.assertFalse(reviewed['unresolvedEssential'])
        self.assertFalse(reviewed['civilCoverageGaps'])

    def test_audit_cannot_write_candidates_into_the_addon(self):
        with self.assertRaises(ValueError): build('unused', ROOT/'addon/data/candidate')


if __name__=='__main__': unittest.main()
