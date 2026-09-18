"""Controls for the workspace-aware ``package://`` resolver.

The resolver exists because ``UNRESOLVED_DEPENDENCY`` meant two different
things: the resource is absent, and the resolver has no model of ROS package
resolution. Separating those is only worth something if the resolver refuses
what it should, so most of this file is negative space -- a resolver that
resolved everything would be as useless as one that resolved nothing.

The central control is :func:`test_no_global_fallback_to_a_package_outside_the_roots`.
A package sitting on disk, findable, with the requested file present, must still
come back ``UNRESOLVED_PACKAGE`` when it was not declared. That is the whole
contract: resolution follows what the caller declared, not what the host has.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from navfm.isaac.ros_package_resolver import (
    RESOLUTION_CLASSES,
    RosPackageResolver,
    parse_package_uri,
)
from navfm.isaac.urdf_import import UrdfImportRefused, parse_source


def make_package(root: Path, name: str, *, declared: str | None = None,
                 files: dict[str, bytes] | None = None) -> Path:
    """Create a package whose identity comes from its manifest."""
    package = root / name
    package.mkdir(parents=True, exist_ok=True)
    (package / "package.xml").write_text(
        '<?xml version="1.0"?>\n<package format="3">\n'
        f"  <name>{declared or name}</name>\n  <version>0.0.1</version>\n"
        "  <description>fixture</description>\n"
        "  <maintainer email='f@example.invalid'>fixture</maintainer>\n"
        "  <license>fixture</license>\n</package>\n")
    for relative, payload in (files or {}).items():
        target = package / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
    return package


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    src = tmp_path / "ws" / "src"
    make_package(src, "alpha", files={"meshes/wheel.stl": b"alpha wheel",
                                      "urdf/alpha.urdf": b"<robot name='a'/>"})
    make_package(src, "beta", files={"meshes/wheel.stl": b"beta wheel"})
    make_package(src / "nested" / "group", "gamma", files={"meshes/arm.stl": b"gamma"})
    return src


# -- URI validation --------------------------------------------------------


@pytest.mark.parametrize("uri", [
    "",
    "file:///tmp/x.stl",
    "meshes/wheel.stl",
    "package://",
    "package:///meshes/wheel.stl",
    "package://alpha",
    "package://alpha/",
    "package://al pha/meshes/wheel.stl",
    "package://../meshes/wheel.stl",
])
def test_malformed_uris_are_refused_structurally(uri: str) -> None:
    with pytest.raises(ValueError):
        parse_package_uri(uri)


def test_a_well_formed_uri_splits_into_package_and_resource() -> None:
    assert parse_package_uri("package://alpha/meshes/wheel.stl") == (
        "alpha", "meshes/wheel.stl")


@pytest.mark.parametrize("uri", [
    "package://",
    "package:///x.stl",
    "package://alpha",
    "package://alpha/",
    "not-a-uri",
])
def test_resolver_reports_malformed_uris_without_raising(
        workspace: Path, uri: str) -> None:
    outcome = RosPackageResolver(source_roots=[workspace]).resolve(uri)
    assert outcome.status == "MALFORMED_PACKAGE_URI"
    assert outcome.reason
    assert outcome.resolved_path is None


# -- source-root resolution ------------------------------------------------


def test_resolves_a_declared_source_package(workspace: Path) -> None:
    outcome = RosPackageResolver(source_roots=[workspace]).resolve(
        "package://alpha/meshes/wheel.stl")
    assert outcome.status == "RESOLVED"
    assert outcome.resolution_class == "SOURCE"
    assert Path(outcome.resolved_path or "").read_bytes() == b"alpha wheel"
    assert outcome.sha256


def test_discovers_packages_at_any_depth(workspace: Path) -> None:
    """Real vendor workspaces nest; a fixed depth would miss gamma."""
    resolver = RosPackageResolver(source_roots=[workspace])
    assert set(resolver.package_names()) == {"alpha", "beta", "gamma"}
    assert resolver.resolve("package://gamma/meshes/arm.stl").resolved


def test_package_identity_comes_from_the_manifest_not_the_directory(
        tmp_path: Path) -> None:
    src = tmp_path / "src"
    make_package(src, "some_directory", declared="actual_package",
                 files={"x.stl": b"x"})
    resolver = RosPackageResolver(source_roots=[src])
    assert resolver.package_names() == ("actual_package",)
    assert resolver.resolve("package://some_directory/x.stl").status == (
        "UNRESOLVED_PACKAGE")
    assert resolver.resolve("package://actual_package/x.stl").resolved
    entry = resolver.inventory()["packages"][0]
    assert entry["directory_name_differs"] is True


def test_a_manifest_without_a_name_registers_nothing(tmp_path: Path) -> None:
    src = tmp_path / "src"
    (src / "broken").mkdir(parents=True)
    (src / "broken" / "package.xml").write_text(
        '<?xml version="1.0"?><package format="3"><version>1</version></package>')
    make_package(src, "good", files={"x.stl": b"x"})
    resolver = RosPackageResolver(source_roots=[src])
    assert resolver.package_names() == ("good",)
    assert len(resolver.inventory()["malformed_manifests"]) == 1


# -- negative space --------------------------------------------------------


def test_no_global_fallback_to_a_package_outside_the_roots(tmp_path: Path) -> None:
    """The file exists, is findable, and must still not resolve.

    This is the control the whole contract rests on: a resolver that quietly
    consults the host would pass every other test in this file.
    """
    allowed = tmp_path / "allowed" / "src"
    make_package(allowed, "alpha", files={"meshes/wheel.stl": b"alpha"})
    elsewhere = tmp_path / "elsewhere" / "src"
    outsider = make_package(elsewhere, "outsider", files={"meshes/wheel.stl": b"out"})
    assert (outsider / "meshes" / "wheel.stl").is_file()

    outcome = RosPackageResolver(source_roots=[allowed]).resolve(
        "package://outsider/meshes/wheel.stl")
    assert outcome.status == "UNRESOLVED_PACKAGE"
    assert outcome.resolved_path is None


def test_environment_variables_cannot_widen_resolution(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Identical result under a deliberately polluted environment."""
    allowed = tmp_path / "allowed" / "src"
    make_package(allowed, "alpha", files={"meshes/wheel.stl": b"alpha"})
    elsewhere = tmp_path / "elsewhere" / "src"
    make_package(elsewhere, "outsider", files={"meshes/wheel.stl": b"out"})

    clean = RosPackageResolver(source_roots=[allowed])
    clean_results = [clean.resolve(u).status for u in
                     ("package://alpha/meshes/wheel.stl",
                      "package://outsider/meshes/wheel.stl")]

    for variable in ("ROS_PACKAGE_PATH", "AMENT_PREFIX_PATH", "CMAKE_PREFIX_PATH",
                     "PYTHONPATH", "COLCON_PREFIX_PATH"):
        monkeypatch.setenv(variable, f"{elsewhere}{os.pathsep}/opt/ros/humble")
    monkeypatch.chdir(elsewhere)

    polluted = RosPackageResolver(source_roots=[allowed])
    polluted_results = [polluted.resolve(u).status for u in
                        ("package://alpha/meshes/wheel.stl",
                         "package://outsider/meshes/wheel.stl")]

    assert clean_results == polluted_results == ["RESOLVED", "UNRESOLVED_PACKAGE"]


def test_a_resolver_with_no_roots_is_refused() -> None:
    """No roots would imply a global fallback, so it cannot be constructed."""
    with pytest.raises(ValueError, match="at least one root"):
        RosPackageResolver()


def test_missing_package_is_distinct_from_missing_resource(workspace: Path) -> None:
    resolver = RosPackageResolver(source_roots=[workspace])
    absent_package = resolver.resolve("package://missing_package/resource.stl")
    absent_resource = resolver.resolve("package://alpha/meshes/absent.stl")
    assert absent_package.status == "UNRESOLVED_PACKAGE"
    assert absent_resource.status == "UNRESOLVED_RESOURCE"
    assert absent_resource.package_root is not None


def test_same_basename_in_two_packages_does_not_confuse_resolution(
        workspace: Path) -> None:
    resolver = RosPackageResolver(source_roots=[workspace])
    alpha = resolver.resolve("package://alpha/meshes/wheel.stl")
    beta = resolver.resolve("package://beta/meshes/wheel.stl")
    assert Path(alpha.resolved_path or "").read_bytes() == b"alpha wheel"
    assert Path(beta.resolved_path or "").read_bytes() == b"beta wheel"
    assert alpha.sha256 != beta.sha256


@pytest.mark.parametrize("resource", [
    "../../outside.stl",
    "meshes/../../../outside.stl",
    "%2e%2e/outside.stl",
    "%2e%2e%2foutside.stl",
    "meshes/%2E%2E/%2E%2E/outside.stl",
])
def test_traversal_is_refused_before_any_read(
        tmp_path: Path, workspace: Path, resource: str) -> None:
    (tmp_path / "outside.stl").write_bytes(b"secret")
    outcome = RosPackageResolver(source_roots=[workspace]).resolve(
        f"package://alpha/{resource}")
    assert outcome.status == "RESOURCE_PATH_TRAVERSAL"
    assert outcome.resolved_path is None


@pytest.mark.parametrize("uri", [
    "package://alpha//etc/hostname",
    "package://alpha/%2Fetc/hostname",
    "package://alpha/C:/Windows/win.ini",
])
def test_absolute_resource_paths_are_refused(workspace: Path, uri: str) -> None:
    """An extra separator or an encoded one must not become a filesystem root."""
    outcome = RosPackageResolver(source_roots=[workspace]).resolve(uri)
    assert outcome.status in {"RESOURCE_PATH_TRAVERSAL", "MALFORMED_PACKAGE_URI"}
    assert outcome.resolved_path is None


def test_an_ordinary_relative_path_stays_inside_the_package_root(
        workspace: Path) -> None:
    """``package://alpha/etc/hostname`` is not a path to /etc/hostname.

    The separator after the package name is the normal one, so this is an
    ordinary relative resource that happens not to exist. The resolver must say
    so, and must not have read anything outside alpha.
    """
    outcome = RosPackageResolver(source_roots=[workspace]).resolve(
        "package://alpha/etc/hostname")
    assert outcome.status == "UNRESOLVED_RESOURCE"
    assert outcome.resolved_path is None
    assert str(workspace / "alpha") == outcome.package_root


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX symlink semantics")
def test_a_symlink_leaving_the_package_root_is_refused(
        tmp_path: Path, workspace: Path) -> None:
    """An in-package-looking path must not read outside the admitted closure."""
    outside = tmp_path / "outside.stl"
    outside.write_bytes(b"outside the closure")
    (workspace / "alpha" / "meshes" / "linked.stl").symlink_to(outside)

    outcome = RosPackageResolver(source_roots=[workspace]).resolve(
        "package://alpha/meshes/linked.stl")
    assert outcome.status == "SYMLINK_ESCAPE"
    assert outcome.resolved_path is None

    admitted = RosPackageResolver(source_roots=[workspace], allow_symlink_escape=True)
    assert admitted.resolve("package://alpha/meshes/linked.stl").resolved


# -- precedence ------------------------------------------------------------


def test_duplicate_package_in_one_precedence_class_refuses(tmp_path: Path) -> None:
    first = tmp_path / "first" / "src"
    second = tmp_path / "second" / "src"
    make_package(first, "alpha", files={"meshes/wheel.stl": b"first"})
    make_package(second, "alpha", files={"meshes/wheel.stl": b"second"})

    resolver = RosPackageResolver(source_roots=[first, second])
    assert resolver.ambiguous_packages() == ("alpha",)
    outcome = resolver.resolve("package://alpha/meshes/wheel.stl")
    assert outcome.status == "PACKAGE_RESOLUTION_AMBIGUOUS"
    assert len(outcome.suppressed_candidates) == 2
    assert outcome.resolved_path is None


def test_ambiguity_does_not_depend_on_root_order(tmp_path: Path) -> None:
    first = tmp_path / "first" / "src"
    second = tmp_path / "second" / "src"
    make_package(first, "alpha", files={"x.stl": b"1"})
    make_package(second, "alpha", files={"x.stl": b"2"})
    forward = RosPackageResolver(source_roots=[first, second])
    reverse = RosPackageResolver(source_roots=[second, first])
    assert (forward.resolve("package://alpha/x.stl").status
            == reverse.resolve("package://alpha/x.stl").status
            == "PACKAGE_RESOLUTION_AMBIGUOUS")


def make_install(root: Path, name: str, files: dict[str, bytes]) -> Path:
    share = root / name / "share" / name
    share.mkdir(parents=True, exist_ok=True)
    (share / "package.xml").write_text(
        f'<?xml version="1.0"?><package format="3"><name>{name}</name>'
        "<version>0.0.1</version></package>")
    for relative, payload in files.items():
        target = share / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
    return share


def test_install_roots_resolve_in_ament_layout(tmp_path: Path) -> None:
    install = tmp_path / "install"
    make_install(install, "alpha", {"meshes/wheel.stl": b"installed"})
    outcome = RosPackageResolver(install_roots=[install]).resolve(
        "package://alpha/meshes/wheel.stl")
    assert outcome.status == "RESOLVED"
    assert outcome.resolution_class == "INSTALL"
    assert Path(outcome.resolved_path or "").read_bytes() == b"installed"


def test_source_wins_over_install_and_records_what_it_suppressed(
        tmp_path: Path) -> None:
    src = tmp_path / "ws" / "src"
    install = tmp_path / "ws" / "install"
    make_package(src, "alpha", files={"meshes/wheel.stl": b"from source"})
    make_install(install, "alpha", {"meshes/wheel.stl": b"from install"})

    resolver = RosPackageResolver(source_roots=[src], install_roots=[install])
    outcome = resolver.resolve("package://alpha/meshes/wheel.stl")
    assert outcome.resolution_class == "SOURCE"
    assert Path(outcome.resolved_path or "").read_bytes() == b"from source"
    assert len(outcome.suppressed_candidates) == 1
    assert "install" in outcome.suppressed_candidates[0]
    assert resolver.ambiguous_packages() == ()


def test_precedence_is_declared_before_use() -> None:
    assert RESOLUTION_CLASSES == ("SOURCE", "INSTALL")


def test_install_semantics_are_not_manufactured(tmp_path: Path) -> None:
    """A directory that is not an ament install tree yields no packages."""
    not_install = tmp_path / "install"
    (not_install / "alpha" / "meshes").mkdir(parents=True)
    (not_install / "alpha" / "meshes" / "wheel.stl").write_bytes(b"x")
    resolver = RosPackageResolver(install_roots=[not_install], source_roots=[tmp_path])
    assert "alpha" not in resolver.package_names()


# -- the parser stays strict ----------------------------------------------


def test_the_parser_still_refuses_package_refs_without_a_contract(
        tmp_path: Path, workspace: Path) -> None:
    """Historical results reproduce: no resolver, same refusal."""
    urdf = tmp_path / "robot.urdf"
    urdf.write_text(
        '<robot name="r"><link name="l"><collision><geometry>'
        '<mesh filename="package://alpha/meshes/wheel.stl"/>'
        "</geometry></collision></link></robot>")
    with pytest.raises(UrdfImportRefused) as refusal:
        parse_source(urdf)
    assert refusal.value.category == "UNRESOLVED_DEPENDENCY"


def test_malformed_xml_stays_refused_however_good_the_resolver_is(
        tmp_path: Path, workspace: Path) -> None:
    """XML conformance is decided before resolution is attempted.

    The local NavFM twin URDF is malformed -- a ``--`` inside a comment, which
    XML 1.0 forbids -- and no workspace may make that parse.
    """
    urdf = tmp_path / "malformed.urdf"
    urdf.write_text(
        '<robot name="r">\n<!-- a comment with -- inside, which XML forbids -->\n'
        '<link name="l"><collision><geometry>'
        '<mesh filename="package://alpha/meshes/wheel.stl"/>'
        "</geometry></collision></link></robot>")
    resolver = RosPackageResolver(source_roots=[workspace])
    for kwargs in ({}, {"resolver": resolver}):
        with pytest.raises(UrdfImportRefused) as refusal:
            parse_source(urdf, **kwargs)  # type: ignore[arg-type]
        assert refusal.value.category == "SOURCE_MALFORMED"


#: The tracked NavFM twin description. XML 1.0 forbids ``--`` inside a comment
#: and this file has one, so it must stay refused no matter how capable the
#: resolver becomes. Asserted present rather than skipped: a regression that
#: skips itself when its subject disappears protects nothing.
MALFORMED_NAVFM_URDF = (
    Path(__file__).resolve().parents[1]
    / "assets/robots/yahboom_m3_pro/yahboom_m3pro.urdf")


def test_the_real_navfm_urdf_stays_refused_for_its_xml_defect(
        workspace: Path) -> None:
    assert MALFORMED_NAVFM_URDF.is_file(), (
        f"{MALFORMED_NAVFM_URDF} is tracked in this repository; if it moved, this "
        "regression must be repointed, never skipped")
    resolver = RosPackageResolver(source_roots=[workspace])
    for kwargs in ({}, {"resolver": resolver}):
        with pytest.raises(UrdfImportRefused) as refusal:
            parse_source(MALFORMED_NAVFM_URDF, **kwargs)  # type: ignore[arg-type]
        assert refusal.value.category == "SOURCE_MALFORMED"


def test_a_resolvable_reference_no_longer_blocks_geometry_validation(
        tmp_path: Path, workspace: Path) -> None:
    """The resolver widens what is checkable, not what is accepted.

    The reference now resolves, so parsing reaches the geometry stage -- and
    refuses there, because a mesh collider cannot be measured.
    """
    urdf = tmp_path / "robot.urdf"
    urdf.write_text(
        '<robot name="r"><link name="l"><collision><geometry>'
        '<mesh filename="package://alpha/meshes/wheel.stl"/>'
        "</geometry></collision></link></robot>")
    resolver = RosPackageResolver(source_roots=[workspace])
    with pytest.raises(UrdfImportRefused) as refusal:
        parse_source(urdf, resolver=resolver)
    assert refusal.value.category == "UNSUPPORTED_COLLISION_PRIMITIVE"


def test_an_unresolvable_reference_still_refuses_with_the_reason(
        tmp_path: Path, workspace: Path) -> None:
    urdf = tmp_path / "robot.urdf"
    urdf.write_text(
        '<robot name="r"><link name="l"><collision><geometry>'
        '<mesh filename="package://nowhere/meshes/wheel.stl"/>'
        "</geometry></collision></link></robot>")
    with pytest.raises(UrdfImportRefused) as refusal:
        parse_source(urdf, resolver=RosPackageResolver(source_roots=[workspace]))
    assert refusal.value.category == "UNRESOLVED_DEPENDENCY"
    assert "UNRESOLVED_PACKAGE" in refusal.value.detail


# -- closure ---------------------------------------------------------------


def test_closure_digest_ignores_where_the_workspace_was_unpacked(
        tmp_path: Path) -> None:
    """The same archive unpacked twice is one closure, not two."""
    from navfm.isaac.urdf_import import source_closure

    digests = []
    for where in ("first", "second"):
        src = tmp_path / where / "src"
        make_package(src, "alpha", files={"meshes/wheel.stl": b"alpha wheel"})
        urdf = tmp_path / where / "robot.urdf"
        urdf.write_text(
            '<robot name="r"><link name="l"><collision><geometry>'
            '<mesh filename="package://alpha/meshes/wheel.stl"/>'
            "</geometry></collision></link></robot>")
        closure = source_closure(urdf, resolver=RosPackageResolver(source_roots=[src]))
        digests.append(closure["closure_digest"])
        assert closure["digest_excludes_host_paths"] is True
    assert digests[0] == digests[1]


def test_closure_digest_changes_when_a_referenced_byte_changes(
        tmp_path: Path) -> None:
    from navfm.isaac.urdf_import import source_closure

    digests = []
    for payload in (b"alpha wheel", b"alpha wheel v2"):
        src = tmp_path / str(len(payload)) / "src"
        make_package(src, "alpha", files={"meshes/wheel.stl": payload})
        urdf = tmp_path / str(len(payload)) / "robot.urdf"
        urdf.write_text(
            '<robot name="r"><link name="l"><collision><geometry>'
            '<mesh filename="package://alpha/meshes/wheel.stl"/>'
            "</geometry></collision></link></robot>")
        closure = source_closure(urdf, resolver=RosPackageResolver(source_roots=[src]))
        digests.append(closure["closure_digest"])
    assert digests[0] != digests[1]
