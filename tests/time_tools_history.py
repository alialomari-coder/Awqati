"""Canonicalize only the approved UI extraction; retain historical AST checks."""
import ast
from copy import deepcopy


def restore_dialog_constructor(tree, class_name):
    tree = deepcopy(tree)
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name)
    constructor = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == '__init__')
    builder = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == '_build_controls')
    # Only the embedded switch may be stripped. Every pre-existing UI statement
    # (including order, names, handlers and close bindings) remains compared.
    body = []
    for node in builder.body:
        if isinstance(node, ast.If) and ast.dump(node.test) == ast.dump(ast.UnaryOp(op=ast.Not(), operand=ast.Name(id='embedded', ctx=ast.Load()))):
            body.extend(node.body)
        else:
            body.append(node)
    constructor.body = constructor.body[:1] + body
    cls.body.remove(builder)
    return tree


def restore_plugin_window_routing(tree, previous):
    tree = deepcopy(tree)
    old_cls = next(n for n in previous.body if isinstance(n, ast.ClassDef))
    old_methods = {n.name: n for n in old_cls.body if isinstance(n, ast.FunctionDef)}
    class Routing(ast.NodeTransformer):
        def visit_ImportFrom(self, node):
            return None if node.module == 'time_tools' else node
        def visit_FunctionDef(self, node):
            if node.name == '_openTimeTool':
                return None
            if node.name in ('_showAlarms', '_showStopwatch'):
                return deepcopy(old_methods[node.name])
            return self.generic_visit(node)
        def visit_Assign(self, node):
            if any(isinstance(t, ast.Attribute) and t.attr == 'time_tools' for t in node.targets):
                return None
            return self.generic_visit(node)
    return Routing().visit(tree)


def strip_world_clock_wiring(test, tree):
    """Remove exactly the reviewed task-3 additions; compare every old node."""
    tree=deepcopy(tree)
    additions=[
        'self._world_clock = None',
        'self._world_clock = WorldClockControl(root, self._runtime, addon_root)',
        'self._runtime.world_clock = self._world_clock',
        'if self._world_clock: self._world_clock.close()',
    ]
    dumps={ast.dump(ast.parse(text).body[0]):0 for text in additions}
    class WorldWiring(ast.NodeTransformer):
        def generic_visit(self,node):
            key=ast.dump(node)
            if key in dumps:
                dumps[key]+=1;return None
            return super().generic_visit(node)
        def visit_ImportFrom(self,node):
            if node.module=='world_clock_control':
                test.assertEqual(['WorldClockControl'],[n.name for n in node.names]);return None
            return node
        def visit_FunctionDef(self,node):
            if node.name=='script_worldClock':return None
            return self.generic_visit(node)
    tree=WorldWiring().visit(tree)
    test.assertEqual([1]*len(dumps),list(dumps.values()))
    return tree
