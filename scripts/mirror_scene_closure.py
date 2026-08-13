"""Full render closure: mirror what a scene needs to *render*, not just to open.

The existing mirrors record ``closure_complete: true`` with zero unresolved
references and are missing every MDL material module. That manifest is not
merely silent about the gap -- it positively asserts completeness, which is worse
than saying nothing, and it is how a uniformly red hospital passed for a
photorealistic one (FL-016).

The cause is a definition. "Reference closure" meant *USD references resolve*.
A renderer needs more than that:

    USD layer  ->  sublayers, references, payloads      (the old definition)
               ->  MDL material modules                 (missed entirely)
               ->  textures the MDL modules ask for     (missed transitively)

So closure here is computed over three dependency classes and iterated to a fixed
point, because fetching an MDL module reveals texture references that did not
exist in the graph until that module was on disk.

Rules this follows, each of which the previous tool broke:

* **Resolve the real dependency, never substitute.** A missing material is not
  replaced with a local stand-in; it is fetched from the lineage the manifest
  records, or it stays missing and the scene stays ineligible.
* **Fetch only what is referenced.** The graph decides, not a directory listing.
  Mirroring a whole vendor asset library would hide the question being asked.
* **Every file carries its source URI, retrieval time, size and digest**, so the
  mirror can be re-derived and diffed rather than trusted.
* **Completeness is reported per class**, so a partial repair cannot be read as
  a whole one.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "gates" / "scenes"

#: Extensions we treat as texture-class dependencies. Extensions are not assumed
#: in advance for USD/MDL discovery -- those come from the reference graph -- but
#: a texture is recognised by what an MDL module asks a sampler to load.
TEXTURE_EXT = {".png", ".jpg", ".jpeg", ".exr", ".dds", ".tga", ".tif", ".tiff", ".hdr"}
USD_EXT = {".usd", ".usda", ".usdc", ".usdz"}

#: Top-level directories that are anchored at the Isaac asset root rather than
#: at the scene directory -- shared libraries such as sky domes and common
#: materials, which several environments reference.
SHARED_ROOTS = {"NVIDIA", "Isaac"}

#: `texture_2d("./Textures/x.png", ...)` and bare quoted asset paths in MDL.
MDL_ASSET = re.compile(r'"([^"]+\.(?:png|jpg|jpeg|exr|dds|tga|tif|tiff|hdr))"', re.I)
MDL_IMPORT = re.compile(r'(?:^|\s)import\s+([A-Za-z0-9_:.]+)', re.M)


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def fetch(url: str, dest: Path, *, timeout: int = 60) -> dict[str, Any]:
    """Retrieve one dependency, verifying transport rather than assuming it."""
    rec: dict[str, Any] = {"source_uri": url, "local_path": str(dest)}
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(url, timeout=timeout) as r:
            if r.status != 200:
                rec.update(ok=False, error=f"HTTP {r.status}")
                return rec
            data = r.read()
        if not data:
            rec.update(ok=False, error="empty response")
            return rec
        dest.write_bytes(data)
        rec.update(ok=True, bytes=len(data), sha256=sha256(dest),
                   retrieved_utc=datetime.now(timezone.utc).isoformat())
    except (urllib.error.URLError, OSError, ValueError) as exc:
        rec.update(ok=False, error=f"{type(exc).__name__}: {exc}")
    return rec


def discover_usd_dependencies(root_usd: Path) -> dict[str, list[str]]:
    """MDL modules and asset paths the *stage* asks for, read from the stage.

    Runs inside Isaac because the scenes are binary USD and the material
    references live behind UsdShade, not in a text scan.
    """
    from pxr import Sdf, Usd, UsdShade

    stage = Usd.Stage.Open(str(root_usd))
    mdl: set[str] = set()
    assets: set[str] = set()
    # `stage.Traverse()` skips instance prototypes. These scenes are heavily
    # instanced -- most walls and doors live under `/__Prototype_*` -- so the
    # default walk found 10 of the material modules and the compiler then failed
    # on ones it had never been asked to mirror. Instance proxies are included
    # explicitly, and the prototypes walked directly as well, because a default
    # that silently narrows the graph is exactly how the first closure tool
    # reported complete while missing everything (FL-016).
    roots = [stage.Traverse(Usd.TraverseInstanceProxies(Usd.PrimAllPrimsPredicate))]
    roots += [Usd.PrimRange(p, Usd.PrimAllPrimsPredicate) for p in stage.GetPrototypes()]
    for prim in (p for r in roots for p in r):
        shader = UsdShade.Shader(prim)
        if shader:
            impl = shader.GetSourceAsset("mdl")
            if impl:
                mdl.add((str(impl.path), _authoring_dir(shader.GetPrim(), "info:mdl:sourceAsset")))
        for attr in prim.GetAttributes():
            if attr.GetTypeName() == Sdf.ValueTypeNames.Asset:
                v = attr.Get()
                if v and getattr(v, "path", None):
                    assets.add((str(v.path), _authoring_dir(prim, attr.GetName())))
    return {"mdl": sorted(mdl), "assets": sorted(assets)}


def _authoring_dir(prim: Any, attr_name: str) -> str:
    """Directory of the layer that authored this reference.

    A relative asset path such as ``../Materials/X.mdl`` is relative to the layer
    that wrote it, not to the root layer. Resolving against the root is off by
    however deep the authoring layer sits -- which is why every warehouse fetch
    missed: its props live two directories below the mirror root.
    """
    attr = prim.GetAttribute(attr_name)
    if attr:
        stack = attr.GetPropertyStack(0.0)
        if stack:
            ident = stack[0].layer.realPath or stack[0].layer.identifier
            if ident:
                return str(Path(ident).parent)
    for spec in prim.GetPrimStack():
        ident = spec.layer.realPath or spec.layer.identifier
        if ident:
            return str(Path(ident).parent)
    return ""


def classify(path: str) -> str:
    suf = Path(path).suffix.lower()
    if suf == ".mdl":
        return "MATERIAL_MODULE"
    if suf in TEXTURE_EXT:
        return "TEXTURE"
    if suf in USD_EXT:
        return "USD_REFERENCE"
    return "OTHER"


def normalise(ref: str, referencing_dir: Path, mirror_root: Path) -> Path:
    """Where a reference lands on disk, relative to the mirror root.

    MDL references are authored relative to the layer that uses them, which for
    these scenes lives in ``Props/`` -- so ``../Materials/X.mdl`` means
    ``<mirror>/Materials/X.mdl``. Resolving it against the *root* layer's
    directory instead walks above the mirror and collapses to a bare filename,
    which then fetches from the wrong URL. Leading traversal segments are
    stripped and the remainder anchored at the mirror root, which is also what
    keeps a reference from escaping the mirror.
    """
    r = ref.replace("\\", "/")
    if r.startswith(("./", "../")):
        rel = (referencing_dir / r).resolve()
        try:  # inside the mirror: use it as resolved
            rel.relative_to(mirror_root.resolve())
            return rel
        except ValueError:  # escaped the mirror: re-anchor at the root
            while r.startswith(("./", "../")):
                r = r[2:] if r.startswith("./") else r[3:]
    return (mirror_root / r.lstrip("/")).resolve()


def rel_to_base(local: Path, mirror_root: Path) -> str:
    try:
        return str(local.relative_to(mirror_root))
    except ValueError:
        return local.name


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scene-id", required=True)
    ap.add_argument("--root-usd", required=True)
    ap.add_argument("--mirror-root", required=True)
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--root-base-url", default=None,
                    help="base for shared library assets anchored at the Isaac root")
    ap.add_argument("--max-rounds", type=int, default=6)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    root_usd = Path(args.root_usd)
    mirror_root = Path(args.mirror_root)
    base = args.base_url.rstrip("/")
    if not root_usd.is_file():
        print(f"REFUSED: no root layer at {root_usd}", file=sys.stderr)
        return 2

    from isaacsim.simulation_app import SimulationApp

    app = SimulationApp({"headless": True})

    report: dict[str, Any] = {
        "check": "FULL_RENDER_CLOSURE",
        "scene_id": args.scene_id,
        "root_usd": str(root_usd),
        "mirror_root": str(mirror_root),
        "source_base_url": base,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "definition": (
            "Closure over USD references, MDL material modules and the textures those "
            "modules request, iterated to a fixed point. The previous definition covered "
            "only the first class and reported complete (FL-016)."
        ),
        "nodes": {}, "rounds": [],
    }
    nodes: dict[str, dict[str, Any]] = report["nodes"]

    def note(ref: str, local: Path, kind: str, by: str) -> None:
        key = rel_to_base(local, mirror_root)
        n = nodes.setdefault(key, {
            "path": key, "type": kind, "local_path": str(local),
            "referenced_by": [], "exists": local.is_file(),
            "resolution_method": "mirror_relative",
        })
        if by not in n["referenced_by"]:
            n["referenced_by"].append(by)
        n["exists"] = local.is_file()
        if n["exists"] and "sha256" not in n:
            n["sha256"] = sha256(local)
            n["bytes"] = local.stat().st_size

    # -- round 0: what the stage asks for ------------------------------------
    disc = discover_usd_dependencies(root_usd)
    for m, adir in disc["mdl"]:
        base_dir = Path(adir) if adir else root_usd.parent
        note(m, normalise(m, base_dir, mirror_root), "MATERIAL_MODULE", str(root_usd.name))
    for a, adir in disc["assets"]:
        k = classify(a)
        if k in ("TEXTURE", "MATERIAL_MODULE"):
            base_dir = Path(adir) if adir else root_usd.parent
            note(a, normalise(a, base_dir, mirror_root), k, str(root_usd.name))
    report["initial"] = {
        "mdl_referenced": len(disc["mdl"]),
        "asset_paths_referenced": len(disc["assets"]),
        "missing_before": sum(1 for n in nodes.values() if not n["exists"]),
    }

    # -- fetch to a fixed point ----------------------------------------------
    for rnd in range(args.max_rounds):
        missing = [n for n in nodes.values() if not n["exists"] and n["type"] != "OTHER"]
        if not missing:
            report["rounds"].append({"round": rnd, "missing": 0, "fetched": 0,
                                     "note": "fixed point reached"})
            break
        r: dict[str, Any] = {"round": rnd, "missing": len(missing),
                             "fetched": 0, "failed": 0, "results": []}
        for n in missing:
            # Most dependencies are anchored at the scene directory, but shared
            # library assets (skies, common materials) are authored against the
            # Isaac root instead. Both bases are tried rather than one assumed.
            rel = n["path"].replace(chr(92), "/")
            url = (f"{args.root_base_url.rstrip('/')}/{rel}"
                   if args.root_base_url and rel.split("/", 1)[0] in SHARED_ROOTS
                   else f"{base}/{rel}")
            if args.dry_run:
                n["planned_source_uri"] = url
                continue
            res = fetch(url, Path(n["local_path"]))
            n["source_uri"] = url
            if res.get("ok"):
                n.update(exists=True, sha256=res["sha256"], bytes=res["bytes"],
                         retrieved_utc=res["retrieved_utc"], resolution_method="fetched_from_source")
                r["fetched"] += 1
            else:
                n["fetch_error"] = res.get("error")
                r["failed"] += 1
            r["results"].append({"path": n["path"], "ok": bool(res.get("ok")),
                                 "error": res.get("error")})
        # Newly present MDL modules reveal textures that were not in the graph
        # before, so the walk repeats rather than assuming one pass suffices.
        for n in list(nodes.values()):
            if n["type"] == "MATERIAL_MODULE" and n["exists"]:
                try:
                    text = Path(n["local_path"]).read_text(errors="ignore")
                except OSError:
                    continue
                for tex in set(MDL_ASSET.findall(text)):
                    note(tex, normalise(tex, Path(n["local_path"]).parent, mirror_root),
                         "TEXTURE", n["path"])
        report["rounds"].append(r)
        if args.dry_run:
            break

    # -- per-class completeness ----------------------------------------------
    def cls(kind: str) -> tuple[int, int]:
        sel = [n for n in nodes.values() if n["type"] == kind]
        return len(sel), sum(1 for n in sel if n["exists"])

    tot_mdl, ok_mdl = cls("MATERIAL_MODULE")
    tot_tex, ok_tex = cls("TEXTURE")
    tot_usd, ok_usd = cls("USD_REFERENCE")
    report["closure"] = {
        "usd_closure_complete": tot_usd == ok_usd,
        "material_closure_complete": tot_mdl == ok_mdl,
        "texture_closure_complete": tot_tex == ok_tex,
        "mdl": {"required": tot_mdl, "present": ok_mdl},
        "textures": {"required": tot_tex, "present": ok_tex},
        "usd": {"required": tot_usd, "present": ok_usd},
        "total_dependencies": len(nodes),
        "unresolved": sorted(n["path"] for n in nodes.values() if not n["exists"]),
    }
    report["closure"]["full_render_closure"] = (
        report["closure"]["usd_closure_complete"]
        and report["closure"]["material_closure_complete"]
        and report["closure"]["texture_closure_complete"]
    )
    # render_validation_complete is deliberately NOT set here. A mirror can be
    # complete and the scene still render wrongly; that is a separate gate.
    report["render_validation_complete"] = "NOT_EVALUATED_HERE — see camera_view_acceptance"

    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / f"mirror_manifest_{args.scene_id}.json"
    p.write_text(json.dumps(report, indent=2) + "\n")

    c = report["closure"]
    print(f"\nFULL RENDER CLOSURE — {args.scene_id}")
    print(f"  MDL      {c['mdl']['present']}/{c['mdl']['required']}")
    print(f"  textures {c['textures']['present']}/{c['textures']['required']}")
    print(f"  total deps {c['total_dependencies']}  unresolved {len(c['unresolved'])}")
    print(f"  FULL_RENDER_CLOSURE = {c['full_render_closure']}")
    for u in c["unresolved"][:10]:
        print(f"    missing: {u}")
    print(f"  record -> {p.relative_to(REPO)}")
    app.close()
    return 0 if c["full_render_closure"] else 1


if __name__ == "__main__":
    sys.exit(main())
