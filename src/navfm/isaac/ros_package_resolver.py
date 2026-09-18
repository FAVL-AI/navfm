"""Resolve ``package://`` URIs against explicitly declared ROS workspace roots.

The strict source parser refused every ``package://`` reference, and that
refusal was recorded as ``UNRESOLVED_DEPENDENCY``. Tracing the vendor
workspaces showed what that category actually meant: the referenced meshes were
present, and the parser had no model of ROS package resolution at all. The
refusal was about the resolver's scope, not about missing files.

The distinction that has to survive this repair is that

    resource exists somewhere in the workspace

is not

    resource resolved according to the declared package-resolution contract

so the fix is a resolver with an explicit contract, never a parser that
searches until something matches. Every root is supplied by the caller. There
is no fallback to ``ROS_PACKAGE_PATH``, ``AMENT_PREFIX_PATH``, the working
directory, or whatever happens to be installed on the host: a resolution that
depends on the machine it ran on is not reproducible evidence.

Package identity comes from ``package.xml``, never from a directory name, so a
directory called ``M3Pro`` is package ``M3Pro`` only because its manifest says
so. Where one name is declared twice inside the same precedence class the
resolver refuses instead of choosing, because every available tie-break --
first hit, alphabetical, newest, nearest -- would make the answer depend on
something that is not the contract.

Resolution is bounded to the package root it resolved. Traversal, absolute
paths, percent-encoded separators and symlinks leaving the root are refused,
since an in-package-looking path that reads outside the admitted closure
defeats the point of hashing a closure.
"""

from __future__ import annotations

import dataclasses
import hashlib
import os
import re
import urllib.parse
import xml.etree.ElementTree as ET
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

__all__ = [
    "RESOLUTION_CLASSES",
    "RESOLUTION_STATUSES",
    "PackageEntry",
    "Resolution",
    "RosPackageResolver",
    "parse_package_uri",
]

#: Precedence order, frozen before any file was evaluated with it. Explicit
#: source roots win over explicit install roots, and nothing else is consulted.
RESOLUTION_CLASSES: tuple[str, ...] = ("SOURCE", "INSTALL")

#: Every outcome the resolver can report. Structured rather than boolean
#: because "package absent" and "package present, resource absent" are
#: different findings about the vendor material and must not collapse.
RESOLUTION_STATUSES: tuple[str, ...] = (
    "RESOLVED",
    "UNRESOLVED_PACKAGE",
    "UNRESOLVED_RESOURCE",
    "PACKAGE_RESOLUTION_AMBIGUOUS",
    "MALFORMED_PACKAGE_URI",
    "RESOURCE_PATH_TRAVERSAL",
    "SYMLINK_ESCAPE",
    "UNSUPPORTED_RESOLUTION_CONTEXT",
)

_SCHEME = "package://"

#: Structural validation only. ROS 2 prefers lowercase names, but the vendor's
#: production package is called ``M3Pro`` and refusing it would be enforcing a
#: style convention against the apparatus that actually exists.
_PACKAGE_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_\-]*$")


@dataclasses.dataclass(frozen=True)
class PackageEntry:
    """One package, identified by the manifest that declares it."""

    name: str
    package_xml: Path
    package_root: Path
    workspace_root: Path
    resolution_class: str
    package_xml_sha256: str
    #: True when the directory is not named after the package it declares --
    #: recorded rather than corrected, because it is a provenance signal.
    directory_name_differs: bool

    def as_record(self, *, relative_to: Path | None = None) -> dict[str, Any]:
        def show(path: Path) -> str:
            if relative_to is not None:
                try:
                    return str(path.relative_to(relative_to))
                except ValueError:
                    pass
            return str(path)

        return {
            "name": self.name,
            "package_xml": show(self.package_xml),
            "package_root": show(self.package_root),
            "workspace_root": str(self.workspace_root),
            "resolution_class": self.resolution_class,
            "package_xml_sha256": self.package_xml_sha256,
            "directory_name_differs": self.directory_name_differs,
        }


@dataclasses.dataclass(frozen=True)
class Resolution:
    """The outcome of resolving one URI, carrying why as well as what."""

    status: str
    uri: str
    package: str | None = None
    requested_resource: str | None = None
    resolution_roots: tuple[str, ...] = ()
    package_root: str | None = None
    resolved_path: str | None = None
    resolution_class: str | None = None
    sha256: str | None = None
    suppressed_candidates: tuple[str, ...] = ()
    reason: str = ""

    @property
    def resolved(self) -> bool:
        return self.status == "RESOLVED"

    def as_record(self) -> dict[str, Any]:
        record = dataclasses.asdict(self)
        record["resolution_roots"] = list(self.resolution_roots)
        record["suppressed_candidates"] = list(self.suppressed_candidates)
        record["resolved"] = self.resolved
        return record


def parse_package_uri(uri: str) -> tuple[str, str]:
    """Split a ``package://`` URI, or state exactly why it is not one.

    Raises ``ValueError`` with a human-readable reason. Nothing is repaired: a
    malformed URI in a vendor description is a fact about the description, and
    rewriting it into a working one would hide that fact.
    """
    if not isinstance(uri, str) or not uri:
        raise ValueError("empty URI")
    if not uri.startswith(_SCHEME):
        raise ValueError(f"does not start with {_SCHEME!r}")

    remainder = uri[len(_SCHEME):]
    if not remainder:
        raise ValueError("no package name or resource path")
    if remainder.startswith("/"):
        raise ValueError("package name is empty (extra separator after the scheme)")

    package, separator, resource = remainder.partition("/")
    if not _PACKAGE_NAME.match(package):
        raise ValueError(f"package name {package!r} is not a valid package name")
    if not separator:
        raise ValueError(f"no resource path after package {package!r}")
    if not resource:
        raise ValueError(f"empty resource path for package {package!r}")
    return package, resource


def _decoded_segments(resource: str) -> list[str]:
    """Segments after one percent-decoding pass, so encoded traversal is seen.

    ``%2e%2e%2f`` is ``../``. Decoding once and re-splitting means the traversal
    check sees what the filesystem would, without the resolver ever rewriting
    the caller's URI.
    """
    decoded = urllib.parse.unquote(resource)
    return [segment for segment in re.split(r"[\\/]+", decoded) if segment]


class RosPackageResolver:
    """Resolve ``package://`` URIs against roots the caller declares.

    ``source_roots`` are workspace directories searched for ``package.xml``
    manifests at any depth, because real vendor workspaces nest packages
    (``src/M3Pro_core/imu_tools/imu_tools``) and a fixed depth would miss them.
    ``install_roots`` are ament install prefixes laid out as
    ``<root>/<package>/share/<package>/``.

    Discovery is eager so that ambiguity is a property of the declared roots
    rather than of the order in which URIs happen to arrive.
    """

    def __init__(
        self,
        source_roots: Iterable[str | os.PathLike[str]] = (),
        install_roots: Iterable[str | os.PathLike[str]] = (),
        *,
        allow_symlink_escape: bool = False,
    ) -> None:
        self._source_roots = tuple(Path(r).resolve() for r in source_roots)
        self._install_roots = tuple(Path(r).resolve() for r in install_roots)
        self._allow_symlink_escape = allow_symlink_escape
        if not self._source_roots and not self._install_roots:
            raise ValueError(
                "a resolver with no roots would resolve nothing and imply a "
                "global fallback that does not exist; supply at least one root")

        self._packages: dict[str, list[PackageEntry]] = {}
        self._malformed_manifests: list[dict[str, str]] = []
        self._discover()

    # -- discovery ---------------------------------------------------------

    def _discover(self) -> None:
        for root in self._source_roots:
            for manifest in self._manifests_under(root):
                self._register(manifest, root, manifest.parent, "SOURCE")
        for root in self._install_roots:
            for manifest in self._install_manifests_under(root):
                self._register(manifest, root, manifest.parent, "INSTALL")

    @staticmethod
    def _manifests_under(root: Path) -> list[Path]:
        """Every ``package.xml`` beneath one declared root, symlinks not followed.

        Bounded by the root and nothing else: no depth assumption, and no step
        outside what the caller declared.
        """
        if not root.is_dir():
            return []
        found: list[Path] = []
        for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
            dirnames[:] = sorted(
                name for name in dirnames if not Path(dirpath, name).is_symlink())
            if "package.xml" in filenames:
                found.append(Path(dirpath, "package.xml"))
        return sorted(found)

    @staticmethod
    def _install_manifests_under(root: Path) -> list[Path]:
        """Manifests in ament install layout, not manufactured where absent."""
        if not root.is_dir():
            return []
        found: list[Path] = []
        for prefix in sorted(p for p in root.iterdir() if p.is_dir()):
            share = prefix / "share"
            if not share.is_dir():
                continue
            for package_dir in sorted(p for p in share.iterdir() if p.is_dir()):
                manifest = package_dir / "package.xml"
                if manifest.is_file():
                    found.append(manifest)
        return sorted(found)

    def _register(
        self, manifest: Path, workspace_root: Path, package_root: Path, cls: str
    ) -> None:
        try:
            raw = manifest.read_bytes()
            declared = ET.fromstring(raw).findtext("name")
        except (OSError, ET.ParseError) as exc:
            self._malformed_manifests.append(
                {"package_xml": str(manifest), "reason": f"unreadable manifest: {exc}"})
            return
        name = (declared or "").strip()
        if not name:
            self._malformed_manifests.append(
                {"package_xml": str(manifest), "reason": "manifest declares no <name>"})
            return
        if not _PACKAGE_NAME.match(name):
            self._malformed_manifests.append(
                {"package_xml": str(manifest),
                 "reason": f"declared name {name!r} is not a valid package name"})
            return
        self._packages.setdefault(name, []).append(PackageEntry(
            name=name,
            package_xml=manifest,
            package_root=package_root,
            workspace_root=workspace_root,
            resolution_class=cls,
            package_xml_sha256=hashlib.sha256(raw).hexdigest(),
            directory_name_differs=package_root.name != name,
        ))

    # -- inspection --------------------------------------------------------

    @property
    def source_roots(self) -> tuple[Path, ...]:
        return self._source_roots

    @property
    def install_roots(self) -> tuple[Path, ...]:
        return self._install_roots

    def package_names(self) -> tuple[str, ...]:
        return tuple(sorted(self._packages))

    def ambiguous_packages(self) -> tuple[str, ...]:
        """Names declared more than once inside one precedence class."""
        ambiguous = []
        for name, entries in self._packages.items():
            for cls in RESOLUTION_CLASSES:
                if len({e.package_root for e in entries
                        if e.resolution_class == cls}) > 1:
                    ambiguous.append(name)
                    break
        return tuple(sorted(ambiguous))

    def inventory(self, *, relative_to: Path | None = None) -> dict[str, Any]:
        packages = [entry.as_record(relative_to=relative_to)
                    for entries in self._packages.values() for entry in entries]
        packages.sort(key=lambda r: (str(r["name"]), str(r["package_root"])))
        return {
            "source_roots": [str(r) for r in self._source_roots],
            "install_roots": [str(r) for r in self._install_roots],
            "precedence": list(RESOLUTION_CLASSES),
            "global_fallback": "DISABLED",
            "package_count": len(self._packages),
            "manifest_count": len(packages),
            "packages": packages,
            "ambiguous_package_names": list(self.ambiguous_packages()),
            "malformed_manifests": list(self._malformed_manifests),
            "identity_source": "package.xml <name>, never the directory name",
        }

    # -- resolution --------------------------------------------------------

    def _roots_record(self) -> tuple[str, ...]:
        return tuple(str(r) for r in (*self._source_roots, *self._install_roots))

    def _select(self, package: str) -> tuple[PackageEntry | None, list[PackageEntry], str]:
        """Apply the frozen precedence, reporting what it suppressed."""
        entries = self._packages.get(package, [])
        if not entries:
            return None, [], "package not declared in any supplied root"
        for cls in RESOLUTION_CLASSES:
            in_class = [e for e in entries if e.resolution_class == cls]
            if not in_class:
                continue
            distinct = {e.package_root for e in in_class}
            if len(distinct) > 1:
                return None, in_class, (
                    f"package {package!r} is declared by {len(distinct)} manifests "
                    f"within precedence class {cls}; the contract names no "
                    "tie-break, so the resolver refuses rather than choosing")
            suppressed = [e for e in entries if e.resolution_class != cls]
            return in_class[0], suppressed, ""
        return None, [], "package declared only in an unsupported resolution class"

    def resolve(self, uri: str) -> Resolution:
        """Resolve one URI to an absolute path, or say precisely why not."""
        roots = self._roots_record()
        try:
            package, resource = parse_package_uri(uri)
        except ValueError as exc:
            return Resolution(status="MALFORMED_PACKAGE_URI", uri=uri,
                              resolution_roots=roots, reason=str(exc))

        segments = _decoded_segments(resource)
        decoded = urllib.parse.unquote(resource)
        if not segments:
            return Resolution(status="MALFORMED_PACKAGE_URI", uri=uri, package=package,
                              requested_resource=resource, resolution_roots=roots,
                              reason="resource path has no segments")
        if decoded.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", decoded):
            return Resolution(status="RESOURCE_PATH_TRAVERSAL", uri=uri, package=package,
                              requested_resource=resource, resolution_roots=roots,
                              reason="resource path is absolute; it must be relative "
                                     "to the package root")
        if any(segment == ".." for segment in segments):
            return Resolution(status="RESOURCE_PATH_TRAVERSAL", uri=uri, package=package,
                              requested_resource=resource, resolution_roots=roots,
                              reason="resource path contains a '..' segment, after one "
                                     "percent-decoding pass")

        entry, suppressed, why = self._select(package)
        suppressed_paths = tuple(str(e.package_root) for e in suppressed)
        if entry is None:
            status = ("PACKAGE_RESOLUTION_AMBIGUOUS" if suppressed
                      else "UNRESOLVED_PACKAGE")
            return Resolution(status=status, uri=uri, package=package,
                              requested_resource=resource, resolution_roots=roots,
                              suppressed_candidates=suppressed_paths, reason=why)

        package_root = entry.package_root
        candidate = package_root.joinpath(*segments)

        # Containment before any read: lexical first, then following symlinks.
        try:
            lexical = Path(os.path.normpath(candidate))
            lexical.relative_to(Path(os.path.normpath(package_root)))
        except ValueError:
            return Resolution(status="RESOURCE_PATH_TRAVERSAL", uri=uri, package=package,
                              requested_resource=resource, resolution_roots=roots,
                              package_root=str(package_root),
                              reason="resource path leaves the package root")

        if not candidate.exists():
            return Resolution(status="UNRESOLVED_RESOURCE", uri=uri, package=package,
                              requested_resource=resource, resolution_roots=roots,
                              package_root=str(package_root),
                              resolution_class=entry.resolution_class,
                              suppressed_candidates=suppressed_paths,
                              reason=f"package {package!r} resolves, but it contains no "
                                     f"{resource!r}")

        real = candidate.resolve()
        real_root = package_root.resolve()
        escapes = not (real == real_root or real_root in real.parents)
        if escapes and not self._allow_symlink_escape:
            return Resolution(status="SYMLINK_ESCAPE", uri=uri, package=package,
                              requested_resource=resource, resolution_roots=roots,
                              package_root=str(package_root),
                              resolution_class=entry.resolution_class,
                              reason=f"{resource!r} resolves through a link to {real}, "
                                     "outside the package root, so it is not inside the "
                                     "admitted source closure")
        if not real.is_file():
            return Resolution(status="UNRESOLVED_RESOURCE", uri=uri, package=package,
                              requested_resource=resource, resolution_roots=roots,
                              package_root=str(package_root),
                              resolution_class=entry.resolution_class,
                              reason=f"{resource!r} exists but is not a regular file")

        return Resolution(
            status="RESOLVED", uri=uri, package=package, requested_resource=resource,
            resolution_roots=roots, package_root=str(package_root),
            resolved_path=str(candidate), resolution_class=entry.resolution_class,
            sha256=hashlib.sha256(real.read_bytes()).hexdigest(),
            suppressed_candidates=suppressed_paths,
            reason="resolved under the frozen precedence")

    def resolve_all(self, uris: Sequence[str]) -> list[Resolution]:
        return [self.resolve(uri) for uri in uris]
