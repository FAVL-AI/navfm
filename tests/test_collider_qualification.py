"""Controls for canonicalisation, coverage measurement and the acceptance contract.

The canonical digest has to be insensitive to how a decomposition was written
down and sensitive to what it describes, so the controls come in pairs: reorder
the vertices, reorder the faces, renumber the indices, and the digest must hold;
move a vertex, flip a winding, change the owning link, and it must move.

The coverage measurements are checked against solids whose answer is known by
construction, because a distance function that is merely plausible is how an
under-covered collider gets admitted.
"""

from __future__ import annotations

import numpy as np
import pytest

from navfm.isaac.collider_qualification import (
    ACCEPTANCE_CONTRACT,
    ConvexPart,
    canonical_digest,
    canonical_part_digest,
    coverage_report,
    distance_to_convex_union,
    distance_to_triangles,
    evaluate_acceptance,
)

CUBE_VERTICES = np.array([[0.0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
                          [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1]])
CUBE_FACES = np.array([[0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7],
                       [0, 1, 5], [0, 5, 4], [2, 3, 7], [2, 7, 6],
                       [0, 4, 7], [0, 7, 3], [1, 2, 6], [1, 6, 5]])


def cube(link: str = "base_link", sha: str = "a" * 64,
         offset: tuple[float, float, float] = (0.0, 0.0, 0.0),
         index: int = 0) -> ConvexPart:
    return ConvexPart(link=link, source_sha256=sha, part_index=index,
                      vertices=CUBE_VERTICES + np.asarray(offset),
                      faces=CUBE_FACES.copy())


# -- canonicalisation: must not move --------------------------------------


def test_reordering_vertices_does_not_change_the_digest() -> None:
    order = np.array([5, 2, 7, 0, 3, 6, 1, 4])
    remap = np.empty(8, dtype=int)
    remap[order] = np.arange(8)
    shuffled = ConvexPart("base_link", "a" * 64, 0,
                          CUBE_VERTICES[order], remap[CUBE_FACES])
    assert canonical_part_digest(shuffled) == canonical_part_digest(cube())


def test_reordering_faces_does_not_change_the_digest() -> None:
    reordered = ConvexPart("base_link", "a" * 64, 0, CUBE_VERTICES,
                           CUBE_FACES[::-1])
    assert canonical_part_digest(reordered) == canonical_part_digest(cube())


def test_rotating_a_face_does_not_change_the_digest() -> None:
    """Winding is preserved, so a rotation is the same triangle."""
    rotated = np.roll(CUBE_FACES, 1, axis=1)
    part = ConvexPart("base_link", "a" * 64, 0, CUBE_VERTICES, rotated)
    assert canonical_part_digest(part) == canonical_part_digest(cube())


def test_part_ordering_does_not_change_the_set_digest() -> None:
    parts = [cube(index=0), cube(offset=(2.0, 0, 0), index=1)]
    assert (canonical_digest(parts)["digest"]
            == canonical_digest(list(reversed(parts)))["digest"])


# -- canonicalisation: must move ------------------------------------------


def test_moving_one_vertex_changes_the_digest() -> None:
    moved = CUBE_VERTICES.copy()
    moved[3, 1] += 1e-9
    part = ConvexPart("base_link", "a" * 64, 0, moved, CUBE_FACES)
    assert canonical_part_digest(part) != canonical_part_digest(cube())


def test_flipping_a_winding_changes_the_digest() -> None:
    """A flipped triangle is a different solid, not a different spelling."""
    flipped = CUBE_FACES.copy()
    flipped[0] = flipped[0][::-1]
    part = ConvexPart("base_link", "a" * 64, 0, CUBE_VERTICES, flipped)
    assert canonical_part_digest(part) != canonical_part_digest(cube())


def test_changing_the_owning_link_changes_the_digest() -> None:
    assert canonical_part_digest(cube(link="arm1")) != canonical_part_digest(cube())


def test_changing_the_source_hash_changes_the_digest() -> None:
    assert (canonical_part_digest(cube(sha="b" * 64))
            != canonical_part_digest(cube()))


def test_no_rounding_is_applied() -> None:
    """A change far below any tolerance still moves the digest."""
    moved = CUBE_VERTICES.copy()
    moved[0, 0] += 1e-15
    part = ConvexPart("base_link", "a" * 64, 0, moved, CUBE_FACES)
    assert canonical_part_digest(part) != canonical_part_digest(cube())


def test_malformed_parts_are_rejected() -> None:
    with pytest.raises(ValueError, match=r"\(N, 3\)"):
        ConvexPart("l", "a" * 64, 0, np.zeros((4, 2)), CUBE_FACES)
    with pytest.raises(ValueError, match=r"\(M, 3\)"):
        ConvexPart("l", "a" * 64, 0, CUBE_VERTICES, np.zeros((4, 4), dtype=int))


# -- distance functions ----------------------------------------------------


def test_a_point_inside_a_cube_is_inside_the_union() -> None:
    d = distance_to_convex_union(np.array([[0.5, 0.5, 0.5]]),
                                 [(CUBE_VERTICES, CUBE_FACES)])
    assert d[0] < 0


def test_a_point_outside_reports_its_true_distance() -> None:
    d = distance_to_convex_union(np.array([[1.25, 0.5, 0.5]]),
                                 [(CUBE_VERTICES, CUBE_FACES)])
    assert np.isclose(d[0], 0.25, atol=1e-9)


def test_a_point_on_the_surface_is_neither_in_nor_out() -> None:
    d = distance_to_convex_union(np.array([[1.0, 0.5, 0.5]]),
                                 [(CUBE_VERTICES, CUBE_FACES)])
    assert abs(d[0]) < 1e-9


def test_the_union_covers_what_either_hull_covers() -> None:
    far = np.array([[2.5, 0.5, 0.5]])
    single = distance_to_convex_union(far, [(CUBE_VERTICES, CUBE_FACES)])
    both = distance_to_convex_union(
        far, [(CUBE_VERTICES, CUBE_FACES), (CUBE_VERTICES + np.asarray([2.0, 0.0, 0.0]), CUBE_FACES)])
    assert single[0] > 0
    assert both[0] < 0


def test_point_to_triangle_distance_is_exact_for_a_known_case() -> None:
    triangle = np.array([[[0.0, 0, 0], [1, 0, 0], [0, 1, 0]]])
    above = distance_to_triangles(np.array([[0.25, 0.25, 0.5]]), triangle)
    assert np.isclose(above[0], 0.5, atol=1e-9)
    on = distance_to_triangles(np.array([[0.25, 0.25, 0.0]]), triangle)
    assert on[0] < 1e-9


def test_distance_is_unchanged_by_chunking() -> None:
    """Chunk size is a performance choice and must not be a numerical one."""
    rng = np.random.default_rng(0)
    points = rng.normal(size=(300, 3))
    triangles = CUBE_VERTICES[CUBE_FACES]
    assert np.allclose(distance_to_triangles(points, triangles, chunk=7),
                       distance_to_triangles(points, triangles, chunk=4096))


def brute_force_distance(points: np.ndarray, triangles: np.ndarray) -> np.ndarray:
    """Every point against every triangle, no pruning. The oracle."""
    from navfm.isaac.collider_qualification import _closest_on_triangles

    a = triangles[:, 0]
    return _closest_on_triangles(
        points, a, triangles[:, 1] - a, triangles[:, 2] - a).min(axis=1)


def test_bounding_sphere_pruning_does_not_change_the_answer() -> None:
    """The prune is an exact bound, so it may change the cost and not the result.

    Checked against an unpruned pass on a deliberately awkward mesh: long thin
    triangles at very different scales, where a sloppy bound would discard the
    true nearest triangle.
    """
    rng = np.random.default_rng(7)
    triangles = np.stack([
        rng.normal(size=(200, 3)) * np.array([10.0, 0.05, 1.0]),
        rng.normal(size=(200, 3)) * np.array([0.01, 5.0, 1.0]),
        rng.normal(size=(200, 3)) * np.array([1.0, 1.0, 20.0]),
    ], axis=1)
    points = rng.normal(size=(120, 3)) * 4.0
    assert np.allclose(distance_to_triangles(points, triangles, chunk=16),
                       brute_force_distance(points, triangles), atol=1e-12)


def test_pruning_matches_brute_force_on_a_degenerate_mesh() -> None:
    """Zero-area triangles must not break the bound or the distance."""
    triangles = np.array([
        [[0.0, 0, 0], [1, 0, 0], [0, 1, 0]],
        [[5.0, 5, 5], [5, 5, 5], [5, 5, 5]],
        [[2.0, 0, 0], [2, 0, 0], [2, 1, 0]],
    ])
    points = np.array([[0.2, 0.2, 1.0], [5.0, 5.0, 4.0], [2.0, 0.5, 0.0]])
    assert np.allclose(distance_to_triangles(points, triangles, chunk=1),
                       brute_force_distance(points, triangles), atol=1e-12)


# -- coverage --------------------------------------------------------------


def test_a_perfect_decomposition_has_no_under_coverage() -> None:
    report = coverage_report(CUBE_VERTICES, CUBE_VERTICES[CUBE_FACES],
                             [(CUBE_VERTICES, CUBE_FACES)])
    assert report["under_coverage_m"]["max"] < 1e-9
    assert report["source_vertices_outside_union"] == 0


def test_a_shrunken_collider_shows_under_coverage() -> None:
    shrunk = (CUBE_VERTICES - 0.5) * 0.8 + 0.5
    report = coverage_report(CUBE_VERTICES, CUBE_VERTICES[CUBE_FACES],
                             [(shrunk, CUBE_FACES)])
    assert report["under_coverage_m"]["max"] > 0.09
    assert report["source_vertices_outside_union"] == 8


def test_an_inflated_collider_shows_over_coverage() -> None:
    inflated = (CUBE_VERTICES - 0.5) * 2.0 + 0.5
    report = coverage_report(CUBE_VERTICES, CUBE_VERTICES[CUBE_FACES],
                             [(inflated, CUBE_FACES)])
    assert report["under_coverage_m"]["max"] < 1e-9
    assert report["over_coverage_m"]["max"] > 0.4


def test_the_max_is_reported_alongside_the_mean() -> None:
    """A local breach must not be averageable away."""
    shrunk = (CUBE_VERTICES - 0.5) * 0.8 + 0.5
    report = coverage_report(CUBE_VERTICES, CUBE_VERTICES[CUBE_FACES],
                             [(shrunk, CUBE_FACES)])
    assert report["under_coverage_m"]["max"] >= report["under_coverage_m"]["mean"]
    assert report["under_coverage_m"]["p95"] is not None


# -- acceptance contract ---------------------------------------------------


def good_entry(under_max: float = 0.0) -> dict[str, object]:
    return {"parts": [1], "coverage": {"under_coverage_m": {"max": under_max}}}


def test_a_complete_deterministic_set_is_accepted() -> None:
    verdict = evaluate_acceptance({"base_link": good_entry()}, {"base_link"}, True)
    assert verdict["ACCEPTED"] is True


def test_non_determinism_fails_the_whole_set() -> None:
    verdict = evaluate_acceptance({"base_link": good_entry()}, {"base_link"}, False)
    assert verdict["ACCEPTED"] is False
    assert verdict["failures"][0]["reason"] == "DETERMINISM_NOT_DEMONSTRATED"


def test_a_missing_link_fails() -> None:
    verdict = evaluate_acceptance({"base_link": good_entry()},
                                  {"base_link", "arm1"}, True)
    assert verdict["ACCEPTED"] is False
    assert verdict["failures"][0]["reason"] == "MISSING_COLLIDER"


def test_an_unexpected_link_fails() -> None:
    verdict = evaluate_acceptance(
        {"base_link": good_entry(), "ghost": good_entry()}, {"base_link"}, True)
    assert verdict["ACCEPTED"] is False
    assert "UNEXPECTED_COLLIDER" in {f["reason"] for f in verdict["failures"]}


def test_under_coverage_beyond_the_limit_fails() -> None:
    limit = ACCEPTANCE_CONTRACT["under_coverage"]["threshold_m"]
    verdict = evaluate_acceptance({"base_link": good_entry(limit * 2)},
                                  {"base_link"}, True)
    assert verdict["ACCEPTED"] is False
    assert verdict["failures"][0]["reason"] == "UNDER_COVERAGE_EXCEEDED"


def test_one_failing_link_fails_the_set_however_many_pass() -> None:
    """No whole-robot score can outvote a role failure."""
    limit = ACCEPTANCE_CONTRACT["under_coverage"]["threshold_m"]
    entries = {f"link{i}": good_entry() for i in range(20)}
    entries["lwheel1"] = good_entry(limit * 10)
    verdict = evaluate_acceptance(entries, set(entries), True)
    assert verdict["ACCEPTED"] is False
    assert [f["link"] for f in verdict["failures"]] == ["lwheel1"]


def test_a_link_with_no_parts_fails() -> None:
    verdict = evaluate_acceptance(
        {"base_link": {"parts": [], "coverage": {"under_coverage_m": {"max": 0.0}}}},
        {"base_link"}, True)
    assert verdict["ACCEPTED"] is False
    assert "NO_CONVEX_PARTS" in {f["reason"] for f in verdict["failures"]}


def test_the_contract_excludes_the_tautological_bounds_test() -> None:
    assert "bounds agreement is excluded" in ACCEPTANCE_CONTRACT["non_tautological"]


def test_metrics_without_a_threshold_are_declared_not_assumed_passing() -> None:
    for key in ("over_coverage", "preprocessing_fidelity"):
        assert ACCEPTANCE_CONTRACT[key]["threshold_m"] is None
        assert ACCEPTANCE_CONTRACT[key]["why_no_threshold"]
