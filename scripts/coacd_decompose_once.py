"""Run one CoACD decomposition in a fresh process and emit its canonical digest.

Determinism is only meaningful across processes: the same call twice inside one
interpreter can share state that a second run on another day would not have. So
this is a separate entry point, invoked once per repetition with its own output
directory and no cache, and it prints a digest rather than returning an object.

Every parameter is passed explicitly, including the ones that match upstream
defaults, so the run is reproducible from the record without needing to know
which CoACD version supplied which default.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys

import numpy as np

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from navfm.isaac.collider_qualification import (  # noqa: E402
    ConvexPart,
    canonical_digest,
)
from navfm.isaac.mesh_geometry import read_binary_stl  # noqa: E402


def indexed_mesh(path: pathlib.Path) -> tuple[np.ndarray, np.ndarray]:
    """STL is a triangle soup; CoACD wants an indexed mesh.

    Vertices are welded by exact value, which is how STL encodes shared corners
    in the first place, so this recovers the topology rather than inventing one.
    """
    triangles = read_binary_stl(path)
    flat = triangles.reshape(-1, 3)
    vertices, inverse = np.unique(flat, axis=0, return_inverse=True)
    return vertices, np.asarray(inverse).reshape(-1, 3)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--link", required=True)
    parser.add_argument("--mesh", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--config", required=True,
                        help="JSON file holding the frozen parameter set")
    arguments = parser.parse_args()

    import coacd

    coacd.set_log_level("error")
    mesh_path = pathlib.Path(arguments.mesh)
    parameters = json.loads(pathlib.Path(arguments.config).read_text())
    source_sha = hashlib.sha256(mesh_path.read_bytes()).hexdigest()

    vertices, faces = indexed_mesh(mesh_path)
    result = coacd.run_coacd(coacd.Mesh(vertices, faces), **parameters)

    parts = [ConvexPart(link=arguments.link, source_sha256=source_sha,
                        part_index=index,
                        vertices=np.asarray(v, dtype=np.float64),
                        faces=np.asarray(f, dtype=np.int64))
             for index, (v, f) in enumerate(result)]

    out = pathlib.Path(arguments.out)
    out.mkdir(parents=True, exist_ok=True)
    arrays: dict[str, np.ndarray] = {}
    for index, part in enumerate(parts):
        arrays[f"v{index}"] = part.vertices
        arrays[f"f{index}"] = part.faces
    # numpy's savez stub maps **kwargs onto allow_pickle, so a typed call is
    # refused even though savez takes named arrays. Runtime behaviour is
    # unaffected; this is a stub limitation, not a defect.
    np.savez(out / "parts.npz", **arrays)  # type: ignore[arg-type]

    digest = canonical_digest(parts)
    raw = hashlib.sha256((out / "parts.npz").read_bytes()).hexdigest()
    print(json.dumps({
        "link": arguments.link,
        "source_sha256": source_sha,
        "source_vertices": int(vertices.shape[0]),
        "source_faces": int(faces.shape[0]),
        "part_count": len(parts),
        "total_part_vertices": int(sum(p.vertices.shape[0] for p in parts)),
        "total_part_faces": int(sum(p.faces.shape[0] for p in parts)),
        "canonical_digest": digest["digest"],
        "raw_file_sha256": raw,
        "output_dir": str(out),
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
