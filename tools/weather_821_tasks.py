"""Narrow final wording checks and build; uses existing unittest/SCons tools."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'tools'), str(ROOT/'tests'),
                str(ROOT/'addon/globalPlugins'), str(ROOT/'.build-deps')]

if __name__ == '__main__':
    task = sys.argv.pop(1)
    if task == 'tests':
        import unittest
        suite = unittest.defaultTestLoader.loadTestsFromNames([
            'test_weather_821', 'test_weather_802.EditorialTests',
            'test_weather_802.SnapshotTests',
        ])
        raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful())
    elif task == 'build':
        import SCons.Script
        sys.argv = ['scons', '-Q']
        SCons.Script.main()
    else:
        import runpy
        runpy.run_path(str(ROOT/'tools'/task), run_name='__main__')
