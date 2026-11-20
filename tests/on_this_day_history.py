"""Strip the explicit dev22 additions for earlier whole-file regression checks.

The real dev22 behavior is covered by test_on_this_day_presentation and the
isolated native probe. All pre-existing methods remain compared to history.
"""
import ast
from copy import deepcopy


def strip_day_wiring(tree):
    class Strip(ast.NodeTransformer):
        def visit_Import(self, node):
            return None if [a.name for a in node.names] == ['config'] else node

        def visit_ImportFrom(self, node):
            return None if node.module and node.module.split('.')[-1].startswith('on_this_day') else node

        def visit_FunctionDef(self, node):
            return None if node.name == 'script_onThisDay' else self.generic_visit(node)

        def visit_Assign(self, node):
            for target in node.targets:
                if ((isinstance(target, ast.Name) and target.id in {'day_service', 'day_speech', 'day_pages'})
                        or (isinstance(target, ast.Attribute) and target.attr == '_on_this_day')):
                    return None
            return self.generic_visit(node)

        def visit_If(self, node):
            if isinstance(node.test, ast.Attribute) and node.test.attr == '_on_this_day':
                return None
            return self.generic_visit(node)
    return Strip().visit(deepcopy(tree))


def strip_day_settings(tree):
    class Strip(ast.NodeTransformer):
        def visit_AnnAssign(self, node):
            if isinstance(node.target, ast.Name) and node.target.id == 'on_this_day_web_page':
                return None
            return node

        def visit_Expr(self, node):
            if isinstance(node.value, ast.Call) and any(
                    isinstance(arg, ast.Constant) and arg.value == 'calendar.onThisDayWebPage'
                    for arg in node.value.args):
                return None
            return self.generic_visit(node)

        def visit_If(self, node):
            if isinstance(node.test, ast.Call) and any(isinstance(a, ast.Name) and a.id == 'calendar_raw' for a in node.test.args):
                return None
            return self.generic_visit(node)

        def visit_Assign(self, node):
            if any(isinstance(t, ast.Name) and t.id == 'calendar_raw' for t in node.targets):
                return None
            return self.generic_visit(node)

        def visit_Call(self, node):
            if isinstance(node.func, ast.Name) and node.func.id == '_object' and node.args and isinstance(node.args[0], ast.Name) and node.args[0].id == 'calendar_raw':
                node.args[0] = ast.parse('root["calendar"]', mode='eval').body
            if isinstance(node.func, ast.Name) and node.func.id == 'CalendarSettings' and len(node.args) == 6:
                node.args.pop()
            return self.generic_visit(node)

        def visit_Set(self, node):
            node.elts = [e for e in node.elts if not (isinstance(e, ast.Constant) and e.value == 'onThisDayWebPage')]
            return self.generic_visit(node)
    return Strip().visit(deepcopy(tree))
