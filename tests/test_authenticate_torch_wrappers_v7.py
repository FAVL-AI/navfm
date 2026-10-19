"""The v7 qualified-name derivation must equal the interpreter's own qualified names.

v7 exists only so that the frozen v6 wrapper authentication can run on Python 3.10, where
code objects carry no ``co_qualname``. Its strictness rests entirely on the derived name being
the name the compiler assigned, so it is checked against two independent oracles:

* every Python version: ``function.__qualname__``, which the compiler sets, for functions in a
  module that exercises each branch of the rule (nesting, ``<locals>``, comprehensions,
  lambdas, explicit ``global``, private-name mangling);
* Python 3.11: ``co_qualname`` for every code object in a broad set of real source files.
  3.11 assigns qualified names with the same compiler rule as 3.10. From 3.12 the compiler
  adds scope kinds (PEP 695 type-parameter scopes) and inlines comprehensions (PEP 709), so
  its names are not the 3.10 rule's; there v7 never derives and must use ``co_qualname``.
"""

from __future__ import annotations

import importlib
import inspect
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import authenticate_torch_wrappers_v7 as v7  # noqa: E402

CASES = '''
def top():
    def inner():
        return [lambda: 0 for _ in range(1)][0]
    class Local:
        def method(self):
            return (lambda: 0)
    return inner, Local, inner(), Local().method()

class Outer:
    def method(self):
        def nested():
            pass
        return nested
    class Inner:
        def deep(self):
            pass
    shout = lambda self: 0
    def __private(self):
        pass
    def get_private(self):
        return self._Outer__private

def declares_global():
    global made_global
    def made_global():
        def inside():
            pass
        return inside
    return made_global

class DeclaresGlobal:
    global class_level_global
    def class_level_global():
        pass

class Mangles:
    global __hidden
    def __hidden():
        pass

def generator_owner():
    return next(g for g in [lambda: 0])

async def coroutine_owner():
    def in_coroutine():
        pass
    return in_coroutine
'''


def _collect_functions(namespace: dict) -> list[types.FunctionType]:
    top, outer = namespace["top"], namespace["Outer"]
    inner, local, inner_lambda, local_lambda = top()
    made_global = namespace["declares_global"]()
    coroutine = namespace["coroutine_owner"]()
    try:
        coroutine.send(None)
    except StopIteration as stop:
        in_coroutine = stop.value
    found = [
        top, inner, local.method, inner_lambda, local_lambda,
        outer.method, outer.method(None), outer.Inner.deep, outer.shout,
        outer._Outer__private, namespace["declares_global"], made_global, made_global(),
        namespace["class_level_global"], namespace["_Mangles__hidden"], namespace["generator_owner"],
        namespace["generator_owner"](), namespace["coroutine_owner"], in_coroutine,
    ]
    assert all(isinstance(f, types.FunctionType) for f in found)
    return found


def test_derived_names_equal_the_compilers_qualnames_on_every_version() -> None:
    code = compile(CASES, "<v7-cases>", "exec", dont_inherit=True)
    derived = list(v7.derived_qualified_codes(code))
    namespace: dict = {}
    exec(code, namespace)
    functions = _collect_functions(namespace)
    for function in functions:
        names = [q for c, q in derived if c == function.__code__]
        assert names == [function.__qualname__], (function.__qualname__, names)
    # The rule's special branches are genuinely exercised, not vacuously absent.
    qualnames = {f.__qualname__ for f in functions}
    assert {
        "top.<locals>.inner",
        "top.<locals>.Local.method",
        "Outer.method.<locals>.nested",
        "Outer.__private",
        "made_global",
        "made_global.<locals>.inside",
        "class_level_global",
        "__hidden",
        "coroutine_owner.<locals>.in_coroutine",
    } <= qualnames


def test_the_public_entry_point_uses_co_qualname_when_present() -> None:
    code = compile(CASES, "<v7-cases>", "exec", dont_inherit=True)
    pairs = list(v7.qualified_codes(code))
    assert len(pairs) == len(list(v7.nested_codes(code)))
    if hasattr(code, "co_qualname"):
        assert all(q == c.co_qualname for c, q in pairs)
    else:
        assert pairs == list(v7.derived_qualified_codes(code))


_STDLIB = [
    "argparse", "asyncio.tasks", "collections", "concurrent.futures.process", "contextlib",
    "dataclasses", "email.message", "enum", "functools", "inspect", "json.decoder",
    "logging", "pathlib", "pickle", "pydoc", "re", "subprocess", "tarfile", "threading",
    "typing", "unittest.case", "urllib.request", "zipfile",
]


def _real_sources() -> list[Path]:
    paths = [Path(inspect.getfile(importlib.import_module(name))) for name in _STDLIB]
    paths += sorted((ROOT / "scripts").glob("*.py"))
    return paths


def test_derived_names_equal_the_interpreters_names_across_real_sources() -> None:
    """3.10: __qualname__ of every function reachable from the imported stdlib modules.
    3.11: co_qualname of every code object in the stdlib files and this repository's scripts.
    3.12+: the derivation is never consulted; v7 must return co_qualname for every code
    object. Each branch executes real assertions."""
    checked = 0
    if sys.version_info >= (3, 12):
        for path in _real_sources():
            code = compile(path.read_text(encoding="utf-8"), str(path), "exec", dont_inherit=True)
            for item, name in v7.qualified_codes(code):
                assert name == item.co_qualname
                checked += 1
    elif sys.version_info >= (3, 11):
        for path in _real_sources():
            code = compile(path.read_text(encoding="utf-8"), str(path), "exec", dont_inherit=True)
            for item, name in v7.derived_qualified_codes(code):
                assert name == item.co_qualname, (str(path), item.co_firstlineno, name, item.co_qualname)
                checked += 1
    else:
        for module_name in _STDLIB:
            module = importlib.import_module(module_name)
            path = Path(inspect.getfile(module))
            code = compile(path.read_text(encoding="utf-8"), str(path), "exec", dont_inherit=True)
            derived = list(v7.derived_qualified_codes(code))
            for function in _reachable_functions(module):
                names = [q for c, q in derived if c == function.__code__]
                if names:
                    assert names == [function.__qualname__], (module_name, function.__qualname__, names)
                    checked += 1
    assert checked > 1000, checked


def _reachable_functions(module: types.ModuleType) -> list[types.FunctionType]:
    seen: set[int] = set()
    found: list[types.FunctionType] = []

    def visit(obj: object, depth: int) -> None:
        if id(obj) in seen or depth > 3:
            return
        seen.add(id(obj))
        if isinstance(obj, types.FunctionType):
            if obj.__module__ == module.__name__ and not hasattr(obj, "__wrapped__"):
                found.append(obj)
            return
        if isinstance(obj, (staticmethod, classmethod)):
            visit(obj.__func__, depth)
            return
        if isinstance(obj, property):
            for f in (obj.fget, obj.fset, obj.fdel):
                if f is not None:
                    visit(f, depth)
            return
        if isinstance(obj, type) and obj.__module__ == module.__name__:
            for value in vars(obj).values():
                visit(value, depth + 1)

    for value in vars(module).values():
        visit(value, 0)
    return found
