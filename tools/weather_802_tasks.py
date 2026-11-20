"""Focused checks/build for 8.0.2 using the existing local dependencies."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'tools'), str(ROOT/'tests'),
                str(ROOT/'addon/globalPlugins'), str(ROOT/'.build-deps')]

if __name__ == '__main__':
    task = sys.argv.pop(1)
    if task == 'tests':
        suite = unittest.defaultTestLoader.loadTestsFromNames([
            'test_weather', 'test_weather_801', 'test_weather_802',
            'test_weather_presses', 'test_daily_synopsis_integration',
            'test_daily_info_service', 'test_daily_info_formatters',
        ])
        raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful())
    elif task == 'build':
        from tools.build_release_docs import main
        main()
        import SCons.Script
        sys.argv = ['scons', '-Q']
        SCons.Script.main()
    else:
        import runpy
        runpy.run_path(str(ROOT/'tools'/task), run_name='__main__')
