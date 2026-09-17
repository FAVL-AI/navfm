"""URDF source parsing, closure and import orchestration for the robot asset.

``robot.py`` has named this module in an error message since before it existed:
Attempt 002 of the terminal-approach intervention reached robot instantiation
and stopped because ``assets/m3pro.usd`` was absent and the converter the
message pointed at had never been written.

This module supplies the half of the conversion that does not need Isaac. It
reads the source description and answers, independently of any importer, what
the robot's collision geometry *should* be. That independence is the point:
F-TWIN-1 recorded Isaac's ``URDFParseAndImportFile`` squaring every box collider
extent, so a correct expectation cannot be derived from the imported result --
it has to come from the source.

Nothing here decides which description is authoritative. That is an apparatus
decision, and this module refuses to admit anything for production unless the
caller supplies authoritative-source provenance it does not itself invent.

No geometry value is hard-coded. Wheel radii, camera offsets and chassis extents
are read from whichever source is passed in, so swapping the source swaps the
expectations with no code change.
"""

from __future__ import annotations

import dataclasses
import hashlib
import math
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

__all__ = [
    "SUPPORTED_PRIMITIVES",
    "CollisionElement",
    "SourceModel",
    "UrdfImportRefused",
    "importer_settings",
    "parse_source",
    "source_closure",
]

#: Primitive types whose dimensions this module can state and check. A source
#: using anything else is refused rather than half-validated: a collider the
#: validator cannot measure is a collider it cannot defend.
SUPPORTED_PRIMITIVES: tuple[str, ...] = ("box", "cylinder", "sphere")

_SUPPORTED_SUFFIXES: tuple[str, ...] = (".urdf", ".xml")


class UrdfImportRefused(RuntimeError):
    """A stated refusal from the import path, carrying a named category.

    Categorised rather than bare, for the reason Attempt 002 made concrete: the
    boundary that stopped it raised a plain ``ValueError`` whose message was
    useful by luck, and the lifecycle recorded it as an escaped exception with
    no classification to act on.
    """

    def __init__(self, category: str, detail: str) -> None:
        super().__init__(f"{category}: {detail}")
        self.category = category
        self.detail = detail


@dataclasses.dataclass(frozen=True)
class CollisionElement:
    """One collision primitive, as the *source* declares it."""

    link: str
    index: int
    primitive: str
    #: box -> (x, y, z); cylinder -> (radius, length); sphere -> (radius,)
    dimensions: tuple[float, ...]
    origin_xyz: tuple[float, float, float]
    origin_rpy: tuple[float, float, float]

    @property
    def identity(self) -> str:
        return f"{self.link}/collision[{self.index}]"

    def as_dict(self) -> dict[str, Any]:
        return {
            "identity": self.identity, "link": self.link, "index": self.index,
            "primitive": self.primitive, "dimensions": list(self.dimensions),
            "origin_xyz": list(self.origin_xyz), "origin_rpy": list(self.origin_rpy),
        }


@dataclasses.dataclass(frozen=True)
class SourceModel:
    """The robot as its description states it, before any importer sees it."""

    robot_name: str
    path: str
    sha256: str
    links: tuple[str, ...]
    joints: tuple[dict[str, Any], ...]
    collisions: tuple[CollisionElement, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "robot_name": self.robot_name, "path": self.path, "sha256": self.sha256,
            "link_count": len(self.links), "links": list(self.links),
            "joint_count": len(self.joints), "joints": [dict(j) for j in self.joints],
            "collision_count": len(self.collisions),
            "collisions": [c.as_dict() for c in self.collisions],
        }


def _floats(text: str | None, count: int, default: tuple[float, ...],
            *, what: str) -> tuple[float, ...]:
    if text is None:
        return default
    parts = text.split()
    if len(parts) != count:
        raise UrdfImportRefused(
            "SOURCE_MALFORMED", f"{what} needs {count} numbers, found {len(parts)}")
    try:
        values = tuple(float(p) for p in parts)
    except ValueError as exc:
        raise UrdfImportRefused(
            "SOURCE_MALFORMED", f"{what} is not numeric: {exc}") from exc
    if any(not math.isfinite(v) for v in values):
        raise UrdfImportRefused(
            "NON_FINITE_GEOMETRY", f"{what} contains a non-finite value: {values}")
    return values


def _primitive(geometry: ET.Element, where: str) -> tuple[str, tuple[float, ...]]:
    for child in geometry:
        if child.tag == "box":
            dims = _floats(child.get("size"), 3, (), what=f"{where} box size")
            if not dims:
                raise UrdfImportRefused(
                    "SOURCE_MALFORMED", f"{where} box has no size")
            return "box", dims
        if child.tag == "cylinder":
            radius = _floats(child.get("radius"), 1, (), what=f"{where} cylinder radius")
            length = _floats(child.get("length"), 1, (), what=f"{where} cylinder length")
            if not radius or not length:
                raise UrdfImportRefused(
                    "SOURCE_MALFORMED", f"{where} cylinder missing radius or length")
            return "cylinder", (radius[0], length[0])
        if child.tag == "sphere":
            radius = _floats(child.get("radius"), 1, (), what=f"{where} sphere radius")
            if not radius:
                raise UrdfImportRefused(
                    "SOURCE_MALFORMED", f"{where} sphere has no radius")
            return "sphere", (radius[0],)
        if child.tag == "mesh":
            raise UrdfImportRefused(
                "UNSUPPORTED_COLLISION_PRIMITIVE",
                f"{where} is a mesh. This module states and checks primitive "
                "dimensions; a mesh collider cannot be validated that way and must "
                "not be admitted on a check that does not cover it")
        raise UrdfImportRefused(
            "UNSUPPORTED_COLLISION_PRIMITIVE",
            f"{where} declares <{child.tag}>, which is not one of "
            f"{list(SUPPORTED_PRIMITIVES)}")
    raise UrdfImportRefused("SOURCE_MALFORMED", f"{where} has no geometry")


def parse_source(path: Path | str) -> SourceModel:
    """Read the description. This is the geometry oracle, and it never imports.

    Expected collider dimensions are taken from here and from nowhere else. A
    value recovered from a defective import -- by inverting a square, say --
    would make the validator agree with the importer rather than with the robot.
    """
    target = Path(path)
    if not target.is_file():
        raise UrdfImportRefused("SOURCE_FILE_ABSENT", f"no source description at {target}")
    if target.suffix.lower() not in _SUPPORTED_SUFFIXES:
        raise UrdfImportRefused(
            "UNSUPPORTED_SOURCE_EXTENSION",
            f"{target.suffix!r} is not one of {list(_SUPPORTED_SUFFIXES)}. Xacro must "
            "be expanded first, and the expansion recorded as its own source")

    raw = target.read_bytes()
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise UrdfImportRefused("SOURCE_MALFORMED", f"{target} does not parse: {exc}") from exc
    if root.tag != "robot":
        raise UrdfImportRefused(
            "SOURCE_MALFORMED", f"root element is <{root.tag}>, expected <robot>")

    unresolved = [
        el.get("filename", "") for el in root.iter()
        if el.tag == "mesh" and str(el.get("filename", "")).startswith("package://")]
    if unresolved:
        raise UrdfImportRefused(
            "UNRESOLVED_DEPENDENCY",
            f"{len(unresolved)} package:// reference(s) cannot be resolved locally; "
            "a source whose geometry is fetched from outside the admitted closure "
            "cannot be hashed as a whole")

    links: list[str] = []
    collisions: list[CollisionElement] = []
    for link in root.findall("link"):
        name = link.get("name")
        if not name:
            raise UrdfImportRefused("SOURCE_MALFORMED", "a <link> has no name")
        if name in links:
            raise UrdfImportRefused(
                "DUPLICATE_LINK_IDENTITY",
                f"link {name!r} is declared more than once; collider ownership "
                "would be ambiguous")
        links.append(name)
        for index, collision in enumerate(link.findall("collision")):
            where = f"{name}/collision[{index}]"
            geometry = collision.find("geometry")
            if geometry is None:
                raise UrdfImportRefused("SOURCE_MALFORMED", f"{where} has no <geometry>")
            primitive, dims = _primitive(geometry, where)
            if any(d <= 0.0 for d in dims):
                raise UrdfImportRefused(
                    "NON_POSITIVE_DIMENSION",
                    f"{where} has a non-positive dimension {dims}; a collider with "
                    "zero or negative extent is not a collider")
            origin = collision.find("origin")
            xyz = _floats(origin.get("xyz") if origin is not None else None, 3,
                          (0.0, 0.0, 0.0), what=f"{where} origin xyz")
            rpy = _floats(origin.get("rpy") if origin is not None else None, 3,
                          (0.0, 0.0, 0.0), what=f"{where} origin rpy")
            collisions.append(CollisionElement(
                link=name, index=index, primitive=primitive, dimensions=dims,
                origin_xyz=(xyz[0], xyz[1], xyz[2]),
                origin_rpy=(rpy[0], rpy[1], rpy[2])))

    if not links:
        raise UrdfImportRefused(
            "ROBOT_HAS_NO_LINKS", f"{target} declares no links")

    joints: list[dict[str, Any]] = []
    for joint in root.findall("joint"):
        parent = joint.find("parent")
        child = joint.find("child")
        joints.append({
            "name": joint.get("name"),
            "type": joint.get("type"),
            "parent": parent.get("link") if parent is not None else None,
            "child": child.get("link") if child is not None else None,
        })

    return SourceModel(
        robot_name=root.get("name") or "<unnamed>",
        path=str(target),
        sha256=hashlib.sha256(raw).hexdigest(),
        links=tuple(links),
        joints=tuple(joints),
        collisions=tuple(collisions),
    )


def source_closure(path: Path | str) -> dict[str, Any]:
    """Every file the description needs, hashed. Measured, never assumed."""
    target = Path(path)
    if not target.is_file():
        raise UrdfImportRefused("SOURCE_FILE_ABSENT", f"no source description at {target}")

    raw = target.read_bytes()
    root = ET.fromstring(raw)
    members = [{"path": str(target), "role": "description",
                "sha256": hashlib.sha256(raw).hexdigest(), "size": len(raw)}]

    referenced: list[str] = []
    for element in root.iter():
        filename = element.get("filename")
        if filename:
            referenced.append(filename)

    missing: list[str] = []
    for filename in referenced:
        resolved = (target.parent / filename).resolve()
        if resolved.is_file():
            data = resolved.read_bytes()
            members.append({"path": str(resolved), "role": "referenced_asset",
                            "sha256": hashlib.sha256(data).hexdigest(),
                            "size": len(data)})
        else:
            missing.append(filename)

    if missing:
        raise UrdfImportRefused(
            "UNRESOLVED_DEPENDENCY",
            f"{len(missing)} referenced asset(s) do not resolve locally: {missing[:3]}")

    digest = hashlib.sha256(
        "\n".join(f"{m['role']}:{m['sha256']}" for m in members).encode()).hexdigest()
    return {
        "member_count": len(members),
        "members": members,
        "closure_digest": digest,
        "external_reference_count": len(referenced),
        "method": "resolved and hashed from the description, not assumed",
    }


def importer_settings(*, distance_scale: float = 1.0,
                      fix_base: bool = False) -> dict[str, Any]:
    """The importer configuration, recorded because it is a scientific input.

    ``distance_scale`` is stated explicitly rather than defaulted silently: it is
    the setting F-TWIN-1 investigated, and a later tranche comparing settings
    needs to know which one produced which asset.
    """
    return {
        "distance_scale": distance_scale,
        "fix_base": fix_base,
        "importer": "isaacsim URDFParseAndImportFile",
        "known_defect": (
            "F-TWIN-1: box collider extents are squared by this importer at "
            "distance_scale=1.0. Cylinder colliders are correct. The raw import is "
            "therefore diagnostic, and admitted collision geometry is reconstructed "
            "from the source"),
    }
