"""Retain old whole-file invariants outside the explicitly approved dev17 edits.

New behavior is tested in test_multi_press_execution; old deferred-selection
unit tests run on the dev16 fixture, which is excluded from the add-on.
"""
import ast
from copy import deepcopy
from pathlib import Path
import subprocess
from textwrap import dedent

ROOT=Path(__file__).resolve().parents[1]
APPROVED={
    '_press','_say','_openTimeTool','_show_text','script_prayerVerification',
    'script_stopwatchInfo','script_stopwatchLaps','script_stopwatchCurrentLap',
    'script_stopwatchReset','script_stopwatchLap','script_stopwatchToggle','script_stopwatchTotal',
    'script_personalAlarmInfo','script_stopPersonalAlarm','script_snoozePersonalAlarm','script_worldClock',
    'script_countdownWindow','script_countdownSelected','script_countdownToggle','script_countdownRestart','script_countdownStopAlert',
    'script_countdownCount','script_countdownNearest',
    'script_stopwatchCopy','script_stopwatchStatus','script_stopwatchCount','script_stopwatchLastLap',
    'script_openSettings','script_toggleAllAlerts','script_repeatLastAlert','script_togglePrimaryCalendar','_toggle',
}

def restore_dev17_plugin(tree):
    from converter_history import strip_converter_wiring
    tree=strip_converter_wiring(tree)
    baseline=ast.parse(subprocess.check_output(['git','show','f141e9a:addon/globalPlugins/awqati/nvda_adapter/plugin.py'],cwd=ROOT).decode('utf8'))
    from on_this_day_history import strip_day_wiring
    tree=strip_day_wiring(tree)
    old_cls=next(n for n in baseline.body if isinstance(n,ast.ClassDef))
    cls=next(n for n in tree.body if isinstance(n,ast.ClassDef))
    # Dev20 adds visibility inspection only. Strip precisely that startup
    # block, retaining the full lifecycle invariant for every other statement.
    startup=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='__init__')
    visibility=ast.parse(dedent('''\
        try:
            import inputCore
            from .legacy_commands import configure_legacy_visibility
            configure_legacy_visibility(type(self), (
                inputCore.manager.userGestureMap, inputCore.manager.localeGestureMap,
            ))
        except Exception:
            logHandler.log.exception("Could not inspect legacy Awqati gesture bindings; command descriptions retained.")
    ''')).body[0]
    matching=[n for n in startup.body if ast.dump(n)==ast.dump(visibility)]
    if len(matching)!=1:
        raise AssertionError('Unexpected dev20 visibility startup block')
    startup.body.remove(matching[0])
    old={n.name:n for n in old_cls.body if isinstance(n,ast.FunctionDef)}
    for name in ('__init__','terminate'):
        current=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name==name)
        expected=deepcopy(old[name])
        expected.body=[n for n in expected.body if '_stopwatch_presses' not in ast.unparse(n)]
        if ast.dump(current)!=ast.dump(expected):raise AssertionError('Unexpected lifecycle edit '+name)
    cls.body=[deepcopy(old[n.name]) if isinstance(n,ast.FunctionDef) and n.name in APPROVED|{'__init__','terminate'} else n
              for n in cls.body if not (isinstance(n,ast.FunctionDef) and n.name in {'script_prayerTimesWindow','script_countdownNext','script_countdownPrevious'})]
    index=next(i for i,n in enumerate(baseline.body) if isinstance(n,ast.ImportFrom) and n.module=='stopwatch_gestures')
    tree.body.insert(index,deepcopy(baseline.body[index]))
    return tree

def legacy_control_bytes(data):
    return data.replace(b'A new lap has been created. Lap {number} completed in {duration}.',
                        b'Lap {number} recorded. Duration: {duration}.')

def legacy_gestures_bytes():
    return subprocess.check_output(['git','show','f141e9a:addon/globalPlugins/awqati/nvda_adapter/stopwatch_gestures.py'],cwd=ROOT)
