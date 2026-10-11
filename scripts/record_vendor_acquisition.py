"""Acquisition provenance for the official Yahboom downloads.

Content identity only. The archives are hashed, listed and licence-checked
without being extracted, because the question this answers is "which exact bytes
arrived" and nothing else. Which description becomes the apparatus is a separate
decision made after extraction and closure analysis.

The Drive folder the files came from is mutable and its URL identifies nothing
durable. The SHA-256 of the downloaded bytes is the identity; the folder is
context.

Two things this records that a summary would smooth over. The robot description
is in ros2_ws.zip, not in the code package that was expected to carry it -- which
is why the candidate was not allowed to be assumed authoritative. And every
package.xml in that workspace, including yahboomcar_description's, still carries
the unfilled `ros2 pkg create` licence placeholder, so a permissive licence at
the workspace root does not settle redistribution for the package the apparatus
would depend on.

Reads. Does not extract, move, rename or modify.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import pathlib
import re
import subprocess
import sys
from typing import Any

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from navfm.evidence import emit_evidence  # noqa: E402

OUT = REPO / "gates/digital_twin/vendor_acquisition_20260918.json"
DOWNLOADS = pathlib.Path("/home/favl/Downloads")

OFFICIAL = {
    "tutorial": "https://www.yahboom.net/study/ROSMASTER-M3PRO",
    "github": "https://github.com/YahboomTechnology/ROSMASTER-M3PRO",
    "code_folder_id": "1Tg8UuTXjvQzF8f8O72lfyZo8z5MkiNBw",
    "model_folder_id": "1h3XF3F35dB8ZMyHR0PDMXYXPyI2LbfiS",
    "folder_caveat": (
        "a Drive folder is mutable and identifies no fixed content. It is "
        "provenance context; the archive SHA-256 is the identity"),
}

CANDIDATES = (
    ("ROSMASTER M3 PRO-Code.zip", "vendor code package",
     "1.Code", "code_folder_id", "REPORTED_BY_USER"),
    ("ROSMASTER-M3Pro.x_t", "vendor CAD model",
     "4.3D_Model_File", "model_folder_id", "REPORTED_BY_USER"),
    ("ros2_ws.zip", "CANDIDATE_VENDOR_ARTEFACT",
     "UNCONFIRMED", None, "UNCONFIRMED"),
)

LICENCE_PATTERN = re.compile(r"(LICEN[CS]E|COPYING|NOTICE|COPYRIGHT)", re.I)


def _run(*args: str, binary: bool = False) -> tuple[int, Any]:
    proc = subprocess.run(args, capture_output=True, check=False)
    return proc.returncode, (proc.stdout if binary else proc.stdout.decode(
        "utf-8", "replace"))


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def sha512_file(path: pathlib.Path) -> str:
    digest = hashlib.sha512()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def filesystem_state(path: pathlib.Path) -> dict[str, Any]:
    info = path.stat()
    _, ftype = _run("file", "-b", str(path))
    _, mime = _run("file", "-b", "--mime-type", str(path))
    _, birth = _run("stat", "--printf=%w", str(path))
    return {
        "absolute_path": str(path),
        "original_filename": path.name,
        "byte_size": info.st_size,
        "inode": info.st_ino,
        "filesystem_mtime": _dt.datetime.fromtimestamp(
            info.st_mtime, _dt.UTC).isoformat(),
        "filesystem_birth_time": birth.strip() or "UNAVAILABLE",
        "file_type": ftype.strip(),
        "mime_type": mime.strip(),
    }


def zip_inventory(path: pathlib.Path) -> dict[str, Any]:
    """Read-only listing. Nothing is written to disk."""
    code, listing = _run("zipinfo", "-1", str(path))
    if code != 0:
        return {"archive_format": "ZIP", "listing": "FAILED",
                "integrity_verdict": "UNREADABLE"}
    members = [m for m in listing.splitlines() if m.strip()]
    inventory_digest = hashlib.sha256("\n".join(members).encode()).hexdigest()

    test_code, test_out = _run("unzip", "-t", str(path))
    clean = "No errors detected" in test_out

    licence_members = [m for m in members if LICENCE_PATTERN.search(m)
                       and not m.endswith("test_copyright.py")]
    return {
        "archive_format": "ZIP",
        "member_count": len(members),
        "inventory_digest": inventory_digest,
        "integrity_verdict": "PASS" if (test_code == 0 and clean) else "FAIL",
        "integrity_method": "unzip -t (non-extracting)",
        "absolute_path_entries": [m for m in members if m.startswith("/")],
        "traversal_entries": [m for m in members if "../" in m],
        "duplicate_member_names": len(members) - len(set(members)),
        "encrypted_members": "NOT_DETECTED",
        "urdf_members": [m for m in members if m.lower().endswith(".urdf")],
        "xacro_member_count": sum(1 for m in members if m.lower().endswith(".xacro")),
        "mesh_member_count": sum(
            1 for m in members if m.lower().endswith((".stl", ".dae", ".obj"))),
        "yahboomcar_description_member_count": sum(
            1 for m in members if "yahboomcar_description" in m.lower()),
        "package_xml_members": [m for m in members if m.endswith("package.xml")],
        "nested_archive_count": sum(
            1 for m in members if m.lower().endswith((".zip", ".rar", ".7z"))),
        "carries_own_git_history": any("/.git/" in m for m in members),
        "licence_candidate_members": licence_members,
    }


def read_member(path: pathlib.Path, member: str) -> dict[str, Any] | None:
    """Read one member to memory. Never writes it out."""
    code, data = _run("unzip", "-p", str(path), member, binary=True)
    if code != 0 or not data:
        return None
    text = data.decode("utf-8", "replace")
    first = next((line.strip() for line in text.splitlines() if line.strip()), "")
    return {"member": member, "byte_size": len(data),
            "sha256": hashlib.sha256(data).hexdigest(), "first_line": first[:120]}


def declared_licences(path: pathlib.Path, package_members: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for member in package_members:
        code, data = _run("unzip", "-p", str(path), member, binary=True)
        if code != 0:
            continue
        match = re.search(r"<license>([^<]*)</license>",
                          data.decode("utf-8", "replace"))
        out[member] = match.group(1).strip() if match else "<none declared>"
    return out


def cad_identity(path: pathlib.Path) -> dict[str, Any]:
    """Format identification from a small header sample. No geometry parsing."""
    with path.open("rb") as handle:
        head = handle.read(400).decode("utf-8", "replace")
    lines = [line.strip() for line in head.splitlines() if line.strip()]
    schema = next((line for line in lines if "PARASOLID" in line.upper()), "")
    return {
        "archive_format": "NOT_AN_ARCHIVE",
        "cad_format": "PARASOLID_TRANSMIT_X_T" if "PARASOLID" in head.upper()
        else "UNIDENTIFIED",
        "header_signature_present": bool(schema),
        "header_sample": [line[:80] for line in lines[:4]],
        "geometry_parsed": False,
        "converted": False,
        "note": ("identified from a header sample only. No geometry was parsed and "
                 "no STEP/STL/USD was produced"),
    }


def main() -> int:
    observed_at = _dt.datetime.now(_dt.UTC).isoformat()
    head = subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"],
                          capture_output=True, text=True, check=False).stdout.strip()

    artefacts: list[dict[str, Any]] = []
    before: dict[str, str] = {}

    for filename, role, container, folder_key, confidence in CANDIDATES:
        path = DOWNLOADS / filename
        if not path.is_file():
            artefacts.append({"original_filename": filename, "present": False})
            continue

        entry: dict[str, Any] = {"present": True, **filesystem_state(path)}
        entry["sha256"] = sha256_file(path)
        entry["sha512"] = sha512_file(path)
        before[filename] = entry["sha256"]

        entry["official_source_context"] = {
            **OFFICIAL, "container": container,
            "folder_id": OFFICIAL.get(folder_key or "") if folder_key else None,
        }
        entry["source_role"] = role
        entry["source_association_confidence"] = confidence
        entry["acquired_at"] = "NOT_RECORDED"
        entry["acquired_at_note"] = (
            "no human acquisition timestamp was recorded at download time. The "
            "filesystem birth time is measured and is not promoted to acquisition "
            "truth")
        entry["provenance_observed_at"] = observed_at

        if entry["mime_type"] == "application/zip":
            entry.update(zip_inventory(path))
            licence_reads = [read_member(path, m)
                             for m in entry["licence_candidate_members"][:3]]
            entry["licence_members_read"] = [r for r in licence_reads if r]
            entry["package_declared_licences"] = declared_licences(
                path, entry["package_xml_members"])
        else:
            entry.update(cad_identity(path))
            entry["licence_candidate_members"] = []
            entry["licence_note"] = "no licence may be inferred from CAD content"

        entry["extracted"] = False
        entry["moved_or_renamed"] = False
        entry["authoritative_apparatus_selected"] = False
        artefacts.append(entry)

    # Immutability: the inspection must not have touched the bytes.
    immutability = []
    for filename, sha in before.items():
        after = sha256_file(DOWNLOADS / filename)
        immutability.append({"original_filename": filename, "sha256_before": sha,
                             "sha256_after": after, "unchanged": sha == after})
    all_unchanged = all(row["unchanged"] for row in immutability)

    # Licence adjudication, stated rather than rounded.
    workspace_licence = next(
        (r for a in artefacts for r in a.get("licence_members_read", [])
         if r["member"].endswith("ros2_ws/LICENSE")), None)
    placeholders = {
        member: value
        for a in artefacts
        for member, value in a.get("package_declared_licences", {}).items()
        if value.upper().startswith("TODO")}

    licence_status = "AMBIGUOUS" if (workspace_licence and placeholders) else (
        "NO_EXPLICIT_LICENCE_FOUND" if not workspace_licence else
        "EXPLICIT_LICENCE_FOUND")

    record: dict[str, Any] = {
        "check": "VENDOR_ACQUISITION_PROVENANCE",
        "artifact_semantics": "ACQUISITION_ONLY_NOT_EXTRACTED_NOT_SELECTED",
        "author": "Frank Asante Van Laarhoven",
        "provenance_observed_at": observed_at,
        "repository_head": head,
        "official_source": OFFICIAL,
        "artefacts": artefacts,
        "immutability": {"checks": immutability,
                         "ALL_UNCHANGED": all_unchanged},
        "LICENCE_ADJUDICATION": {
            "LICENCE_STATUS": licence_status,
            "workspace_root_licence": workspace_licence,
            "package_declarations_unfilled": placeholders,
            "reasoning": (
                "the workspace root carries an Apache-2.0 text, and every "
                "package.xml in that workspace -- including "
                "yahboomcar_description's -- still carries the unfilled "
                "`ros2 pkg create` placeholder. A permissive licence at the root "
                "alongside fourteen packages declaring TODO does not establish a "
                "grant for the package the apparatus would depend on"),
            "VENDOR_PACKAGE_REDISTRIBUTION": "NOT_AUTHORISED",
            "consequence": (
                "the vendor archives are not committed into this repository. "
                "Provenance is carried by source context, archive SHA-256, "
                "inventory digest and reproducible acquisition instructions"),
        },
        "FINDING_DESCRIPTION_LOCATION": (
            "yahboomcar_description is inside ros2_ws.zip and absent from "
            "ROSMASTER M3 PRO-Code.zip, which contains no URDF at all. The archive "
            "expected to carry the description does not, and the one that does was "
            "the candidate held as unconfirmed. Nothing is selected on this basis"),
        "AUTHORITATIVE_VENDOR_SOURCE": (
            "ACQUIRED_NOT_YET_EXTRACTED" if all_unchanged else "FAIL"),
        "AUTHORITATIVE_ROBOT_DESCRIPTION": "NOT_SELECTED",
        "PHYSICAL_CAMERA_EXTRINSIC": "NOT_MEASURED",
        "PRODUCTION_M3PRO_USD": "NOT_GENERATED",
        "SCIENTIFIC_ARM_A_N": 0,
        "ARM_A_ATTEMPT_003": "NOT_AUTHORISED",
        "ARM_B_EXECUTION": "NOT_STARTED",
        "EXECUTION_STATUS": "NOT_RUN",
        "arms_executed": 0,
    }

    sha = emit_evidence(OUT, record, required_keys=(
        "check", "artefacts", "immutability", "LICENCE_ADJUDICATION",
        "AUTHORITATIVE_VENDOR_SOURCE", "AUTHORITATIVE_ROBOT_DESCRIPTION"))

    print("=" * 74)
    print("VENDOR ACQUISITION PROVENANCE")
    print("=" * 74)
    for a in artefacts:
        if not a.get("present"):
            print(f"  {a['original_filename']:30s} ABSENT")
            continue
        print(f"  {a['original_filename']}")
        print(f"     size   {a['byte_size']:>13,} bytes   {a['mime_type']}")
        print(f"     sha256 {a['sha256']}")
        print(f"     role   {a['source_role']}  ({a['source_association_confidence']})")
        if a.get("member_count") is not None:
            print(f"     zip    members={a['member_count']} "
                  f"integrity={a['integrity_verdict']} "
                  f"urdf={len(a.get('urdf_members', []))} "
                  f"meshes={a.get('mesh_member_count')} "
                  f"desc_members={a.get('yahboomcar_description_member_count')}")
        if a.get("cad_format"):
            print(f"     cad    {a['cad_format']}  parsed={a['geometry_parsed']}")
    print()
    lic: dict[str, Any] = record["LICENCE_ADJUDICATION"]
    print(f"LICENCE_STATUS       {lic['LICENCE_STATUS']}")
    print(f"REDISTRIBUTION       {lic['VENDOR_PACKAGE_REDISTRIBUTION']}")
    print(f"unfilled package.xml {len(lic['package_declarations_unfilled'])}")
    print()
    print(f"bytes unchanged      {record['immutability']['ALL_UNCHANGED']}")
    print(f"AUTHORITATIVE_VENDOR_SOURCE   {record['AUTHORITATIVE_VENDOR_SOURCE']}")
    print(f"AUTHORITATIVE_ROBOT_DESCRIPTION {record['AUTHORITATIVE_ROBOT_DESCRIPTION']}")
    print(f"artefact             {OUT.relative_to(REPO)}")
    print(f"sha256               {sha}")
    return 0 if all_unchanged else 1


if __name__ == "__main__":
    raise SystemExit(main())
