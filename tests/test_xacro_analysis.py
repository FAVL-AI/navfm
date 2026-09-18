"""Controls for the Xacro static analyser and its expansion contract.

Expanding a Xacro executes vendor-authored code, so the admissibility check is
the thing that has to work. Most of this file is therefore cases that must be
refused: a missing include, an argument with no default, a package that is not
in the declared roots, a command substitution, an environment lookup, and an
include reaching outside the closure.

The environment controls matter most. A file that expands only because
``AMENT_PREFIX_PATH`` happened to point somewhere is not a measurement of the
vendor source, so the analyser's answers must not move when those variables do.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from navfm.isaac.ros_package_resolver import RosPackageResolver
from navfm.isaac.xacro_analysis import (
    XacroRefused,
    admissibility,
    analyse,
    include_closure,
)

HEADER = '<?xml version="1.0"?>\n<robot xmlns:xacro="http://www.ros.org/wiki/xacro"'


def write(path: Path, body: str, *, name: str = "r") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f'{HEADER} name="{name}">\n{body}\n</robot>\n')
    return path


def make_package(root: Path, name: str, files: dict[str, str]) -> Path:
    package = root / name
    package.mkdir(parents=True, exist_ok=True)
    (package / "package.xml").write_text(
        f'<?xml version="1.0"?><package format="3"><name>{name}</name>'
        "<version>0.0.1</version></package>")
    for relative, text in files.items():
        target = package / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
    return package


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    src = tmp_path / "ws" / "src"
    make_package(src, "robot_description", {
        "urdf/base.urdf": '<?xml version="1.0"?><robot name="base">'
                          '<link name="base_link"/></robot>',
    })
    return src


# -- analysis is pure ------------------------------------------------------


def test_analysis_reports_what_the_file_declares(tmp_path: Path) -> None:
    source = write(tmp_path / "r.xacro", """
    <xacro:arg name="positions_file" default="initial.yaml"/>
    <xacro:arg name="required_thing"/>
    <xacro:include filename="$(find robot_description)/urdf/base.urdf"/>
    <xacro:property name="scale" value="1.0"/>
    <xacro:macro name="wheel" params="side"/>
    <xacro:if value="${scale > 0}"><link name="l"/></xacro:if>
    """)
    analysis = analyse(source)
    assert analysis.declares_xacro_namespace is True
    assert analysis.robot_name == "r"
    assert analysis.macros == ("wheel",)
    assert analysis.properties == ("scale",)
    assert analysis.package_references == ("robot_description",)
    assert len(analysis.includes) == 1
    assert {str(a["name"]) for a in analysis.args} == {
        "positions_file", "required_thing"}
    assert len(analysis.conditionals) == 1


def test_analysis_never_executes_anything(tmp_path: Path) -> None:
    """A command substitution is reported, not run."""
    canary = tmp_path / "canary"
    source = write(tmp_path / "r.xacro",
                   f'<xacro:property name="p" value="$(command touch {canary})"/>')
    analysis = analyse(source)
    assert [s["kind"] for s in analysis.unsafe_substitutions] == ["command"]
    assert not canary.exists()


def test_file_reading_expressions_are_named(tmp_path: Path) -> None:
    """``${load_yaml(...)}`` is legal and is a closure question worth naming."""
    source = write(tmp_path / "r.xacro",
                   '<xacro:property name="p" value="${load_yaml(f)[\'k\']}"/>')
    analysis = analyse(source)
    assert len(analysis.file_reading_expressions) == 1


def test_malformed_xacro_is_refused(tmp_path: Path) -> None:
    bad = tmp_path / "bad.xacro"
    bad.write_text('<robot xmlns:xacro="http://www.ros.org/wiki/xacro"><link></robot>')
    with pytest.raises(XacroRefused) as refusal:
        analyse(bad)
    assert refusal.value.category == "SOURCE_MALFORMED"


def test_absent_xacro_is_refused(tmp_path: Path) -> None:
    with pytest.raises(XacroRefused) as refusal:
        analyse(tmp_path / "nothing.xacro")
    assert refusal.value.category == "SOURCE_FILE_ABSENT"


# -- include closure -------------------------------------------------------


def test_include_closure_resolves_find_and_relative_includes(
        tmp_path: Path, workspace: Path) -> None:
    write(tmp_path / "control.xacro", '<xacro:macro name="m" params="n"/>')
    root = write(tmp_path / "root.xacro", """
    <xacro:include filename="$(find robot_description)/urdf/base.urdf"/>
    <xacro:include filename="control.xacro"/>
    """)
    closure = include_closure(
        root, resolver=RosPackageResolver(source_roots=[workspace]))
    assert closure["unresolved"] == []
    assert closure["member_count"] == 3
    assert closure["include_closure_digest"]


def test_include_closure_digest_ignores_where_it_was_unpacked(
        tmp_path: Path) -> None:
    digests = []
    for where in ("first", "second"):
        src = tmp_path / where / "src"
        make_package(src, "robot_description", {
            "urdf/base.urdf": '<robot name="base"><link name="l"/></robot>'})
        root = write(tmp_path / where / "root.xacro",
                     '<xacro:include filename="$(find robot_description)/urdf/base.urdf"/>')
        digests.append(include_closure(
            root, resolver=RosPackageResolver(source_roots=[src]))[
                "include_closure_digest"])
    assert digests[0] == digests[1]


def test_a_cyclic_include_terminates(tmp_path: Path) -> None:
    write(tmp_path / "a.xacro", '<xacro:include filename="b.xacro"/>')
    write(tmp_path / "b.xacro", '<xacro:include filename="a.xacro"/>')
    closure = include_closure(tmp_path / "a.xacro")
    assert closure["unresolved"] == []
    assert closure["member_count"] == 2


# -- negative controls -----------------------------------------------------


def test_a_missing_include_is_recorded_not_ignored(tmp_path: Path) -> None:
    root = write(tmp_path / "root.xacro", '<xacro:include filename="absent.xacro"/>')
    closure = include_closure(root)
    assert [u["category"] for u in closure["unresolved"]] == ["INCLUDE_ABSENT"]
    assert admissibility(analyse(root), closure)["ADMISSIBLE_FOR_EXPANSION"] is False


def test_an_unresolvable_package_refuses(tmp_path: Path, workspace: Path) -> None:
    root = write(tmp_path / "root.xacro",
                 '<xacro:include filename="$(find not_declared)/urdf/x.urdf"/>')
    closure = include_closure(
        root, resolver=RosPackageResolver(source_roots=[workspace]))
    assert [u["category"] for u in closure["unresolved"]] == ["UNRESOLVED_PACKAGE"]


def test_find_without_a_resolution_contract_refuses(tmp_path: Path) -> None:
    root = write(tmp_path / "root.xacro",
                 '<xacro:include filename="$(find anything)/x.urdf"/>')
    closure = include_closure(root)
    assert [u["category"] for u in closure["unresolved"]] == [
        "NO_PACKAGE_RESOLUTION_CONTRACT"]


def test_an_include_needing_an_undeclared_argument_refuses(tmp_path: Path) -> None:
    root = write(tmp_path / "root.xacro",
                 '<xacro:include filename="$(arg which)/x.urdf"/>')
    closure = include_closure(root)
    assert [u["category"] for u in closure["unresolved"]] == ["UNDECLARED_ARGUMENT"]


def test_a_source_defined_default_satisfies_an_argument(tmp_path: Path) -> None:
    write(tmp_path / "chosen.xacro", '<link name="l"/>')
    root = write(tmp_path / "root.xacro", """
    <xacro:arg name="which" default="chosen.xacro"/>
    <xacro:include filename="$(arg which)"/>
    """)
    closure = include_closure(root)
    assert closure["unresolved"] == []
    assert admissibility(analyse(root), closure)["ADMISSIBLE_FOR_EXPANSION"] is True


def test_duplicate_package_ambiguity_blocks_a_find(tmp_path: Path) -> None:
    first, second = tmp_path / "a" / "src", tmp_path / "b" / "src"
    make_package(first, "robot_description", {"urdf/base.urdf": "<robot/>"})
    make_package(second, "robot_description", {"urdf/base.urdf": "<robot/>"})
    root = write(tmp_path / "root.xacro",
                 '<xacro:include filename="$(find robot_description)/urdf/base.urdf"/>')
    closure = include_closure(
        root, resolver=RosPackageResolver(source_roots=[first, second]))
    assert [u["category"] for u in closure["unresolved"]] == ["UNRESOLVED_PACKAGE"]
    assert "AMBIGUOUS" in closure["unresolved"][0]["reason"]


@pytest.mark.parametrize("substitution", [
    "$(command echo hi)",
    "$(env SOME_HOST_VARIABLE)",
])
def test_host_reaching_substitutions_are_inadmissible(
        tmp_path: Path, substitution: str) -> None:
    root = write(tmp_path / "root.xacro",
                 f'<xacro:property name="p" value="{substitution}"/>')
    verdict = admissibility(analyse(root), include_closure(root))
    assert verdict["ADMISSIBLE_FOR_EXPANSION"] is False
    assert any("reaches the host" in r for r in verdict["reasons_refused"])


def test_an_include_escaping_the_workspace_does_not_resolve_through_a_package(
        tmp_path: Path, workspace: Path) -> None:
    """``$(find pkg)`` plus traversal must not become a path outside the closure.

    The escape target sits outside both the declared workspace and the root
    file's own directory, so nothing legitimately admits it. A package that
    resolves is not a path that stays inside it.
    """
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "outside.urdf").write_text('<robot name="o"/>')
    root = write(tmp_path / "project" / "root.xacro",
                 '<xacro:include filename="$(find robot_description)'
                 '/../../../../outside/outside.urdf"/>')
    closure = include_closure(
        root, resolver=RosPackageResolver(source_roots=[workspace]))
    assert [m["name"] for m in closure["members"]] == ["root.xacro"]
    assert [u["category"] for u in closure["unresolved"]] == [
        "INCLUDE_OUTSIDE_CLOSURE"]


def test_an_include_inside_the_root_files_own_directory_is_admitted(
        tmp_path: Path) -> None:
    """The counterpart: a sibling include is ordinary and must still resolve."""
    write(tmp_path / "project" / "sibling.xacro", '<link name="l"/>')
    root = write(tmp_path / "project" / "root.xacro",
                 '<xacro:include filename="sibling.xacro"/>')
    closure = include_closure(root)
    assert closure["unresolved"] == []
    assert sorted(m["name"] for m in closure["members"]) == [
        "root.xacro", "sibling.xacro"]


def test_every_refusal_reason_is_listed_not_only_the_first(tmp_path: Path) -> None:
    root = write(tmp_path / "root.xacro", """
    <xacro:arg name="needed"/>
    <xacro:include filename="absent.xacro"/>
    <xacro:property name="p" value="$(command echo hi)"/>
    """)
    verdict = admissibility(analyse(root), include_closure(root))
    assert verdict["ADMISSIBLE_FOR_EXPANSION"] is False
    assert len(verdict["reasons_refused"]) == 3


def test_a_file_without_the_xacro_namespace_is_inadmissible(tmp_path: Path) -> None:
    plain = tmp_path / "plain.xacro"
    plain.write_text('<?xml version="1.0"?><robot name="r"><link name="l"/></robot>')
    verdict = admissibility(analyse(plain), include_closure(plain))
    assert verdict["ADMISSIBLE_FOR_EXPANSION"] is False


# -- environment independence ---------------------------------------------


@pytest.mark.parametrize("variable", [
    "AMENT_PREFIX_PATH", "ROS_PACKAGE_PATH", "CMAKE_PREFIX_PATH",
    "COLCON_PREFIX_PATH", "PYTHONPATH",
])
def test_analysis_and_closure_do_not_move_with_host_ros_variables(
        tmp_path: Path, workspace: Path, monkeypatch: pytest.MonkeyPatch,
        variable: str) -> None:
    elsewhere = tmp_path / "elsewhere" / "src"
    make_package(elsewhere, "not_declared", {"urdf/x.urdf": "<robot/>"})
    root = write(tmp_path / "root.xacro", """
    <xacro:include filename="$(find robot_description)/urdf/base.urdf"/>
    <xacro:include filename="$(find not_declared)/urdf/x.urdf"/>
    """)

    def measure() -> tuple[str, list[str]]:
        closure = include_closure(
            root, resolver=RosPackageResolver(source_roots=[workspace]))
        return (closure["include_closure_digest"],
                [u["category"] for u in closure["unresolved"]])

    clean = measure()
    monkeypatch.setenv(variable, f"{elsewhere}:/opt/ros/humble")
    monkeypatch.chdir(elsewhere)
    assert measure() == clean
    assert clean[1] == ["UNRESOLVED_PACKAGE"]
