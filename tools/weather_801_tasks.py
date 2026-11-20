"""Use the existing embedded Python and build dependencies without installing anything."""
from pathlib import Path
import sys
import runpy
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'tools'), str(ROOT/'tests'), str(ROOT/'addon/globalPlugins'), str(ROOT/'.build-deps')]
task = sys.argv.pop(1)
if task == 'build':
    from tools.build_release_docs import main
    main()
    import SCons.Script
    sys.argv = ['scons', '-Q']
    SCons.Script.main()
else:
    runpy.run_path(str(ROOT / 'tools' / task), run_name='__main__')
