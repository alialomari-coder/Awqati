"""Remove only the exact approved task-5 wiring from older AST comparisons.

Every expected node must occur exactly once. Any change to that wiring, or any
unrelated lifecycle edit, still fails. Behavioral coverage stays in converter
integration tests and the installed-bundle NVDA gate.
"""
import ast
from copy import deepcopy

EXPECTED = '''
from .calendar_converter_control import CalendarConverterControl, ConverterPresses
self._converter = None
self._converter = CalendarConverterControl(settings, now, zones, lunar,
    self._language, ui.message, gui.mainFrame)
self._converter.presses = ConverterPresses(wx.CallLater,
    lambda: config.conf["keyboard"]["multiPressTimeout"],
    self._converter_binding_active, lambda advanced: self._converter.show(advanced))
if self._converter: self._converter.close()
def _converter_binding_active(self, identifiers):
    from keyboardHandler import KeyboardInputGesture
    if self._terminated:
        return False
    for identifier in identifiers:
        try:
            gesture = KeyboardInputGesture.fromName(identifier.split(":", 1)[1])
            if scriptHandler.findScript(gesture) == self.script_openDateConverter:
                return True
        except (ValueError, LookupError):
            continue
    return False
@scriptHandler.script(description=_("Open date converter"), category=CATEGORY)
def script_openDateConverter(self, gesture):
    if self._converter and not self._terminated:
        self._converter.presses.press(gesture.normalizedIdentifiers,
            scriptHandler.getLastScriptRepeatCount())
'''


def strip_converter_wiring(tree):
    expected = {ast.dump(n): 0 for n in ast.parse(EXPECTED).body}
    keyword = ast.dump(ast.parse('f(show_converter=self._converter.show)').body[0].value.keywords[0])
    expected[keyword] = 0
    class Strip(ast.NodeTransformer):
        def generic_visit(self, node):
            key = ast.dump(node)
            if key in expected:
                expected[key] += 1
                return None
            return super().generic_visit(node)
    result = Strip().visit(deepcopy(tree))
    if any(count != 1 for count in expected.values()):
        raise AssertionError('Unexpected converter wiring: ' + repr(expected))
    return result
