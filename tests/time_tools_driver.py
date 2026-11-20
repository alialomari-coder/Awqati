"""Load UI definitions with injectable NVDA/wx boundaries, preserving method code."""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADAPTER = ROOT / 'addon/globalPlugins/awqati/nvda_adapter'


def definitions(filename, namespace, names=None):
    tree = ast.parse((ADAPTER / filename).read_text('utf-8-sig'))
    body = [n for n in tree.body if isinstance(n, (ast.ClassDef, ast.FunctionDef)) and (names is None or n.name in names)]
    if names is None:
        body = [n for n in tree.body if isinstance(n, (ast.ClassDef, ast.FunctionDef, ast.Assign))]
    exec(compile(ast.Module(body=body, type_ignores=[]), filename, 'exec'), namespace)
    return namespace
