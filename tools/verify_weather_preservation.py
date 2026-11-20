"""Compare protected source and legacy gesture methods with the immutable 7.1.0 ZIP."""
import ast
import hashlib
import json
from pathlib import Path
import zipfile
ROOT = Path(__file__).resolve().parents[1]


def methods(source, class_name):
    tree = ast.parse(source)
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name)
    return {node.name: ast.dump(node, include_attributes=False) for node in cls.body if isinstance(node, ast.FunctionDef)}


def main():
    package = ROOT / "dist/awqati-7.1.0.nvda-addon"
    checked, differences = [], []
    with zipfile.ZipFile(package) as archive:
        for name in archive.namelist():
            if not name.endswith(".py") or not name.startswith("globalPlugins/awqati/"): continue
            relative = name.removeprefix("globalPlugins/awqati/")
            if relative.startswith(("domain/", "application/", "infrastructure/")) and relative not in ("domain/settings.py", "infrastructure/settings_repository.py"):
                current = ROOT / "addon" / name
                checked.append(name)
                if current.read_bytes() != archive.read(name): differences.append(name)
        legacy = methods(archive.read("globalPlugins/awqati/nvda_adapter/plugin.py").decode("utf-8"), "GlobalPlugin")
        current = methods((ROOT / "addon/globalPlugins/awqati/nvda_adapter/plugin.py").read_text("utf-8"), "GlobalPlugin")
        unchanged = [name for name in legacy if name.startswith("script_") or name == "_press"]
        changed_methods = [name for name in unchanged if legacy[name] != current.get(name)]
    result = dict(stableSha256=hashlib.sha256(package.read_bytes()).hexdigest(), protectedFiles=len(checked),
                  protectedDifferences=differences, legacyCommands=len(unchanged), changedLegacyCommands=changed_methods,
                  stableHashMatchesStudy=hashlib.sha256(package.read_bytes()).hexdigest() == "9684debf537389370652fe132419a6aa492451ab473ef66cfdc38357bc446e67")
    (ROOT / "docs/weather_task2/preservation.json").write_text(json.dumps(result, indent=2), "utf-8")
    print(json.dumps(result))
    assert not differences and not changed_methods and result["stableHashMatchesStudy"]

if __name__ == "__main__": main()
