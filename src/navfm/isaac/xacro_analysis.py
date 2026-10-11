"""Read a Xacro without running it, and decide whether running it is admissible.

Xacro is a macro language that evaluates Python expressions and can shell out,
so expanding a vendor file is executing vendor-authored code. That is fine when
it is a deliberate, recorded act and dangerous when it is a side effect of
"inventorying the sources", which is why analysis and expansion are two steps
here rather than one.

Analysis is pure: it reads the XML and reports what the file would need --
includes, macros, properties, arguments, conditionals, package lookups,
environment lookups, file reads inside expressions, and command substitution.
Nothing is resolved and nothing is executed.

Admissibility is then a separate judgement against a declared closure. A file
is admissible only when every include lands inside the workspace roots the
caller declared, every argument has a value or a source-defined default, and
nothing reaches for the host -- no command substitution, no environment
variable without a default. The vendor's own MoveIt files read a YAML file from
inside a ``${...}`` expression, which is legal and worth naming, because a
"pure" macro expansion that opens files is a closure question rather than a
syntax one.

The repository's own capability stops at analysis and include-closure
resolution, both of which are deterministic and testable here. Actually running
xacro needs a xacro installation, and on this machine that exists only inside a
host ROS tree, so any expansion it produces is labelled with what supplied it
rather than presented as reproducible from the repository alone.
"""

from __future__ import annotations

import dataclasses
import hashlib
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - import cycle avoidance only
    from navfm.isaac.ros_package_resolver import RosPackageResolver

__all__ = [
    "SUBSTITUTION_KINDS",
    "UNSAFE_SUBSTITUTIONS",
    "XACRO_NS",
    "XacroAnalysis",
    "XacroRefused",
    "admissibility",
    "analyse",
    "include_closure",
]

XACRO_NS = "http://www.ros.org/wiki/xacro"

#: ``$(...)`` forms xacro understands. Recorded by kind so a reader can see what
#: a file reaches for without reading the file.
SUBSTITUTION_KINDS: tuple[str, ...] = (
    "find", "arg", "env", "optenv", "eval", "command", "dirname", "cwd")

#: Forms that execute a program or read host state with no declared default.
#: Their presence makes a file inadmissible for expansion outright: there is no
#: version of "expand it carefully" that makes running a vendor-chosen command
#: a reproducible measurement. ``optenv`` is deliberately absent -- it carries
#: its own default, so it states a fallback rather than depending on the host.
UNSAFE_SUBSTITUTIONS: tuple[str, ...] = ("command", "env")

_SUBSTITUTION = re.compile(r"\$\((?P<kind>[a-zA-Z_]+)(?P<rest>[^)]*)\)")
_EXPRESSION = re.compile(r"\$\{(?P<body>[^}]*)\}")
#: Calls inside ``${...}`` that touch the filesystem rather than compute.
_FILE_READING_CALLS = ("load_yaml", "xacro.load_yaml", "open", "read")


class XacroRefused(RuntimeError):
    """A stated refusal from the xacro path, carrying a named category."""

    def __init__(self, category: str, detail: str) -> None:
        super().__init__(f"{category}: {detail}")
        self.category = category
        self.detail = detail


@dataclasses.dataclass(frozen=True)
class XacroAnalysis:
    """What a Xacro file declares and what it would reach for. Nothing run."""

    path: Path
    sha256: str
    byte_size: int
    declares_xacro_namespace: bool
    robot_name: str | None
    includes: tuple[str, ...]
    macros: tuple[str, ...]
    properties: tuple[str, ...]
    args: tuple[dict[str, str | None], ...]
    conditionals: tuple[str, ...]
    substitutions: tuple[dict[str, str], ...]
    expressions: tuple[str, ...]
    package_references: tuple[str, ...]
    file_reading_expressions: tuple[str, ...]
    unsafe_substitutions: tuple[dict[str, str], ...]

    def as_record(self) -> dict[str, Any]:
        record = dataclasses.asdict(self)
        record["path"] = str(self.path)
        for key in ("includes", "macros", "properties", "conditionals",
                    "expressions", "package_references",
                    "file_reading_expressions"):
            record[key] = list(getattr(self, key))
        record["args"] = [dict(a) for a in self.args]
        record["substitutions"] = [dict(s) for s in self.substitutions]
        record["unsafe_substitutions"] = [dict(s) for s in self.unsafe_substitutions]
        return record


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def analyse(path: Path | str) -> XacroAnalysis:
    """Read one Xacro and report what it declares. Pure: nothing is executed."""
    target = Path(path)
    if not target.is_file():
        raise XacroRefused("SOURCE_FILE_ABSENT", f"no xacro source at {target}")

    raw = target.read_bytes()
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise XacroRefused("SOURCE_MALFORMED", f"{target} does not parse: {exc}") from exc

    text = raw.decode("utf-8", errors="replace")
    includes: list[str] = []
    macros: list[str] = []
    properties: list[str] = []
    args: list[dict[str, str | None]] = []
    conditionals: list[str] = []

    for element in root.iter():
        tag = _local(element.tag)
        if tag == "include":
            includes.append(str(element.get("filename", "")))
        elif tag == "macro":
            macros.append(str(element.get("name", "")))
        elif tag == "property":
            properties.append(str(element.get("name", "")))
        elif tag == "arg":
            args.append({"name": str(element.get("name", "")),
                         "default": element.get("default")})
        elif tag in {"if", "unless"}:
            conditionals.append(f"{tag}: {element.get('value', '')}")

    substitutions = [
        {"kind": m.group("kind"), "text": m.group(0),
         "argument": m.group("rest").strip()}
        for m in _SUBSTITUTION.finditer(text)]
    expressions = [m.group("body").strip() for m in _EXPRESSION.finditer(text)]

    return XacroAnalysis(
        path=target,
        sha256=hashlib.sha256(raw).hexdigest(),
        byte_size=len(raw),
        declares_xacro_namespace=XACRO_NS in text,
        robot_name=root.get("name"),
        includes=tuple(includes),
        macros=tuple(macros),
        properties=tuple(properties),
        args=tuple(args),
        conditionals=tuple(conditionals),
        substitutions=tuple(substitutions),
        expressions=tuple(expressions),
        package_references=tuple(sorted({
            s["argument"] for s in substitutions if s["kind"] == "find"})),
        file_reading_expressions=tuple(
            e for e in expressions
            if any(call in e for call in _FILE_READING_CALLS)),
        unsafe_substitutions=tuple(
            s for s in substitutions if s["kind"] in UNSAFE_SUBSTITUTIONS),
    )


def _admitted_roots(
    root: Path, resolver: RosPackageResolver | None
) -> tuple[Path, ...]:
    """The closure an include may land in: declared roots, plus the root's own tree.

    Without this an include may resolve a package correctly and then climb out
    of it, because ``$(find pkg)`` yields a directory and whatever follows is
    joined to it unchecked. A package that resolves is not the same as a path
    that stays inside one.
    """
    roots = [root.parent.resolve()]
    if resolver is not None:
        roots.extend(resolver.source_roots)
        roots.extend(resolver.install_roots)
    return tuple(roots)


def _within(candidate: Path, roots: tuple[Path, ...]) -> bool:
    return any(candidate == r or r in candidate.parents for r in roots)


def _resolve_include(
    filename: str, origin: Path, resolver: RosPackageResolver | None,
    supplied_args: dict[str, str], admitted: tuple[Path, ...],
) -> tuple[Path | None, str]:
    """Resolve one include the way xacro would, within the declared closure."""
    target = filename

    def substitute(match: re.Match[str]) -> str:
        kind, rest = match.group("kind"), match.group("rest").strip()
        if kind == "arg":
            if rest in supplied_args:
                return supplied_args[rest]
            raise XacroRefused(
                "UNDECLARED_ARGUMENT",
                f"include needs $(arg {rest}) and no value or default was supplied")
        if kind == "find":
            if resolver is None:
                raise XacroRefused(
                    "NO_PACKAGE_RESOLUTION_CONTRACT",
                    f"include needs $(find {rest}) and no resolver was supplied")
            probe = resolver.resolve(f"package://{rest}/package.xml")
            if probe.package_root is None:
                raise XacroRefused(
                    "UNRESOLVED_PACKAGE",
                    f"$(find {rest}) does not resolve under the declared roots "
                    f"({probe.status})")
            return probe.package_root
        raise XacroRefused(
            "UNSUPPORTED_SUBSTITUTION",
            f"$({kind} {rest}) is not admissible in an include path")

    target = _SUBSTITUTION.sub(substitute, target)
    candidate = Path(target)
    if not candidate.is_absolute():
        candidate = origin.parent / candidate
    candidate = Path(candidate).resolve()
    if not _within(candidate, admitted):
        raise XacroRefused(
            "INCLUDE_OUTSIDE_CLOSURE",
            f"include resolves to {candidate}, which is outside every admitted "
            "root; a package that resolves is not a path that stays inside it")
    if not candidate.is_file():
        return None, f"include resolves to {candidate}, which is not a file"
    return candidate, "resolved"


def include_closure(
    path: Path | str,
    *,
    resolver: RosPackageResolver | None = None,
    args: dict[str, str] | None = None,
    _seen: set[Path] | None = None,
    _admitted: tuple[Path, ...] | None = None,
) -> dict[str, Any]:
    """Every file the Xacro pulls in, transitively, hashed.

    Deterministic and repository-owned: it needs no xacro installation, so the
    include graph can be recorded on a machine that cannot expand anything.
    Cycles terminate rather than recurse.
    """
    target = Path(path).resolve()
    seen = set() if _seen is None else _seen
    supplied = dict(args or {})
    admitted = (_admitted if _admitted is not None
                else _admitted_roots(target, resolver))

    if target in seen:
        return {"members": [], "unresolved": [], "cycle": True}
    seen.add(target)

    analysis = analyse(target)
    for arg in analysis.args:
        name = str(arg["name"])
        if name not in supplied and arg["default"] is not None:
            supplied[name] = str(arg["default"])

    members: list[dict[str, Any]] = [{
        "path": str(target), "name": target.name, "role": "root" if _seen is None
        else "include", "sha256": analysis.sha256, "size": analysis.byte_size}]
    unresolved: list[dict[str, str]] = []

    for filename in analysis.includes:
        try:
            resolved, why = _resolve_include(
                filename, target, resolver, supplied, admitted)
        except XacroRefused as refusal:
            unresolved.append({"include": filename, "category": refusal.category,
                               "reason": refusal.detail})
            continue
        if resolved is None:
            unresolved.append({"include": filename, "category": "INCLUDE_ABSENT",
                               "reason": why})
            continue
        nested = include_closure(resolved, resolver=resolver, args=supplied,
                                 _seen=seen, _admitted=admitted)
        members.extend(nested["members"])
        unresolved.extend(nested["unresolved"])

    canonical = sorted(f"{m['name']}:{m['sha256']}" for m in members)
    return {
        "members": members,
        "unresolved": unresolved,
        "member_count": len(members),
        "include_closure_digest": hashlib.sha256(
            "\n".join(canonical).encode()).hexdigest(),
        "digest_excludes_host_paths": True,
        "cycle": False,
    }


def admissibility(
    analysis: XacroAnalysis,
    closure: dict[str, Any],
    *,
    supplied_args: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Decide whether expanding this file would be a reproducible measurement.

    Every reason is listed rather than short-circuiting on the first, because a
    file with three problems and a file with one are different situations and a
    reader should not have to re-run the check to learn which they have.
    """
    supplied = dict(supplied_args or {})
    reasons: list[str] = []

    if not analysis.declares_xacro_namespace:
        reasons.append("the file does not declare the xacro namespace")
    if analysis.unsafe_substitutions:
        kinds = sorted({s["kind"] for s in analysis.unsafe_substitutions})
        reasons.append(
            f"reaches the host through $({'), $('.join(kinds)}), which cannot be "
            "made reproducible")
    if closure.get("unresolved"):
        reasons.append(
            f"{len(closure['unresolved'])} include(s) do not resolve inside the "
            "declared closure")
    missing = [str(a["name"]) for a in analysis.args
               if a["default"] is None and str(a["name"]) not in supplied]
    if missing:
        reasons.append(f"argument(s) {missing} have no default and none was supplied")

    notes: list[str] = []
    if analysis.file_reading_expressions:
        notes.append(
            f"{len(analysis.file_reading_expressions)} expression(s) read a file "
            "during expansion; the closure must cover what they read")
    if analysis.expressions:
        notes.append(
            "expansion evaluates the file's ${...} expressions, so it executes "
            "vendor-authored code by design")

    return {
        "ADMISSIBLE_FOR_EXPANSION": not reasons,
        "reasons_refused": reasons,
        "notes": notes,
        "contract": [
            "every include lands inside the declared workspace closure",
            "package roots are explicit",
            "arguments are supplied or have source-defined defaults",
            "no command substitution and no environment lookup without a default",
        ],
    }
