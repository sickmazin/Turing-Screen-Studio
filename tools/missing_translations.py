"""Lists UI strings that have no Italian translation yet. Run: python tools/missing_translations.py"""
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import i18n  # noqa: E402
import main  # noqa: E402
import settings  # noqa: E402
import sources  # noqa: E402
import widgets  # noqa: E402


def calls_to_underscore(path):
    """String literals passed to _() and the first item of ("Label", ...) tuples that are later translated."""
    out = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "_" and node.args:
            if isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                out.add(node.args[0].value)
        if isinstance(node, ast.Tuple) and node.elts and isinstance(node.elts[0], ast.Constant) \
                and isinstance(node.elts[0].value, str) and node.elts[0].value[:1].isupper():
            out.add(node.elts[0].value)
    return out


found = set()
for f in ("settings.py", "editor.py", "main.py", "widgets.py", "layout.py", "stock_picker.py"):
    found |= calls_to_underscore(ROOT / f)
for cls in widgets.WIDGETS.values():
    found.add(cls.label)
    found |= {label for _k, _t, _d, label in cls.props}
found |= set(settings.ORIENT_LABELS.values()) | set(settings.COLOR_LABELS.values()) | set(settings.SOURCE_LABELS.values())
for m in main.load(sources).values():
    found |= set(getattr(m, "settings", {}))
missing = sorted(s for s in found if s not in i18n.IT and any(c.isalpha() for c in s))
for s in missing:
    print(repr(s))
print(len(missing), "missing")
