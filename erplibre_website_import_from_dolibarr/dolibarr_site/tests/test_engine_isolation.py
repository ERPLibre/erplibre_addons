# Copyright 2026 TechnoLibre (https://technolibre.ca)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Static check that the engine package never depends on Odoo."""

import ast
import pathlib
import unittest

ENGINE = pathlib.Path(__file__).resolve().parent.parent


def _imported_roots(tree):
    """Yield (lineno, root module name) for every import in a module.

    Relative imports are skipped: they stay inside the engine. Calls to
    __import__() and importlib.import_module() with a literal name count
    as imports.
    """
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield node.lineno, alias.name.split(".")[0]
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            yield node.lineno, (node.module or "").split(".")[0]
        elif isinstance(node, ast.Call) and node.args:
            func = node.func
            name = getattr(func, "attr", getattr(func, "id", ""))
            first = node.args[0]
            if name in ("__import__", "import_module") and isinstance(
                first, ast.Constant
            ):
                yield node.lineno, str(first.value).split(".")[0]


class EngineIsolationCases:
    def _offenders(self, forbidden, skip_tests):
        offenders = []
        for path in sorted(ENGINE.rglob("*.py")):
            rel = path.relative_to(ENGINE)
            if skip_tests and "tests" in rel.parts:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
            for lineno, root in _imported_roots(tree):
                if root in forbidden:
                    offenders.append("%s:%d %s" % (rel, lineno, root))
        return offenders

    def test_engine_never_imports_odoo(self):
        self.assertEqual(self._offenders({"odoo"}, skip_tests=False), [])

    def test_unittest_only_under_tests(self):
        self.assertEqual(self._offenders({"unittest"}, skip_tests=True), [])


class TestEngineIsolation(EngineIsolationCases, unittest.TestCase):
    pass
