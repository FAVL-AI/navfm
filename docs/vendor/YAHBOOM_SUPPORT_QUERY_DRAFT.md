# Yahboom support query — DRAFT, NOT SENT

Status: **DRAFT**. Not sent. Sending is a separate authorisation.
Prepared: 2026-09-18 · Updated: 2026-09-18 after the authority decision
Evidence: `gates/digital_twin/production_description_chain_20260918.json`,
`gates/digital_twin/production_description_inventory_20260918.json`,
`gates/digital_twin/robot_description_authority_20260918.json`

This draft was deliberately held until the production package and file were
identified, so that the query names an exact asset rather than asking Yahboom a
generic question they cannot action.

Since the first draft, `M3Pro/urdf/m3pro.urdf` has been selected as the
whole-robot runtime authority, and a second description was found that MoveIt
loads instead. The query now asks Yahboom to confirm both, because a vendor
confirmation would close the one thing our own evidence cannot: what they
*intend* each file to be.

## What the query can now name precisely

| | |
|---|---|
| Product | ROSMASTER M3 Pro (Jetson Orin NX SUPER-16GB) |
| Workspace | `M3Pro_ws` v0.0.1, as shipped on the Orin |
| Package | `M3Pro` |
| File | `src/M3Pro/urdf/m3pro.urdf` |
| sha256 | `cb092310636677ab4bc9846efd30c39cbf4d953ae4fc140a411d8b4c2e56ae6e` |
| Size | 24836 bytes |
| Loaded by | `m3pro_bringup/launch/car_base.launch.py`, lines 31–37 |
| Meshes | 20 STL files in `src/M3Pro/meshes/` |
| Our classification | `WHOLE_ROBOT_RUNTIME_AUTHORITY` |
| Rival description | `yahboom_M3Pro_description/urdf/M3Pro.urdf`, sha256 `5a96608c…`, in `yahboomcar_ws` |
| Rival's role | loaded by `M3Pro_config` (MoveIt), classified `MANIPULATOR_PLANNING_AUTHORITY` |

## Draft message

> Subject: ROSMASTER M3 Pro — licence and dimensional source for `M3Pro/urdf/m3pro.urdf`
>
> Hello,
>
> I am a doctoral researcher at Newcastle University using a ROSMASTER M3 Pro
> (Jetson Orin) for published robotics research. I am building a simulation model
> of the robot and I need to be able to state, in a paper, where the model came
> from and under what terms it is used.
>
> I am working from the workspace shipped on the robot, `M3Pro_ws`. The URDF the
> robot actually loads at bringup is `M3Pro/urdf/m3pro.urdf`, together with the
> 20 STL meshes in `M3Pro/meshes/`. I have four questions about exactly those
> files.
>
> **0. Which description is the production robot model?** I want to confirm
> my reading before I build anything on it. On the robot, `m3pro_bringup`'s
> `car_base.launch.py` loads `M3Pro/urdf/m3pro.urdf` and passes it to
> `robot_state_publisher`, so I have taken that file to be the production robot
> description for the Orin NX SUPER-16GB in the base + arm + camera
> configuration. Is that correct?
>
> I also found a second, different description at
> `yahboom_M3Pro_description/urdf/M3Pro.urdf` in the `yahboomcar_ws` workspace,
> which your `M3Pro_config` MoveIt package loads through
> `MoveItConfigsBuilder`. It is not the same file: it has 20 links to the other's
> 18, it names the camera link `DCW2` rather than `camera_link`, it adds an
> `arm_base_Link` and a second `Camera` joint on `base_link`, and its four wheel
> joints are `revolute` where the bringup description has them `fixed`. Is that
> second file intended as a separate arm-planning model for MoveIt, or is one of
> the two superseded? Knowing which you consider current would settle it.
>
> Two smaller things I noticed in the same files, mentioned only in case they
> are unintentional. `M3Pro_robot1.urdf` and `M3Pro_robot2.urdf` reference
> `meshes/arM3Pro.STL`, which does not exist; `meshes/arm3.STL` does, and the
> name looks like a find-and-replace of the product name. And the MoveIt
> description references a package `dofbot_M3Pro_descripton` that I cannot find
> in either workspace. I have not changed either file.
>
> **1. Licence.** `M3Pro/package.xml` declares Apache 2.0, but that manifest
> still carries TurtleBot3 metadata — the description reads "Gazebo simulation
> package for the TurtleBot3", the maintainer is listed as
> `willson@robotis.com`, and the repository URLs point at
> `ROBOTIS-GIT/turtlebot3_simulations`. It appears to be a ROBOTIS manifest that
> was copied and renamed, so I do not want to assume it states Yahboom's terms.
> Could you confirm the licence that actually applies to `m3pro.urdf` and the
> `M3Pro/meshes/` STL files? I would like to redistribute a derived simulation
> asset in a public research repository, with attribution, and I need to know
> whether that is permitted.
>
> **2. Collision geometry.** Every collision element in `m3pro.urdf` reuses the
> visual STL mesh, which is the normal output of the SolidWorks URDF exporter.
> For stable simulation I need primitive collision shapes instead. Do you publish
> a version with primitive colliders, or the nominal dimensions (chassis
> envelope, wheel radius and width, arm link lengths) that I could use to build
> them? Deriving them by measuring the meshes is possible but I would rather cite
> your figures than my estimates.
>
> **3. Camera mounting.** In `m3pro.urdf` the depth camera attaches through
> `DCW2_Joint`, a fixed joint whose parent is `arm4`, so the camera is carried by
> the arm rather than the chassis. Could you confirm that this matches the
> shipped hardware configuration, and confirm the intended `arm4` → camera
> optical-frame transform? The URDF encodes
> `xyz = -0.0483883323542816 0.00245180097510241 0.0671900000306381`,
> `rpy = 1.84287098025439 -1.57079631189374 -1.81447538896515`.
> I want to know whether that is a specified mounting or a value that fell out of
> the CAD export, since I intend to verify it against the physical robot.
>
> **4. CAD source.** The URDF header records that it was exported from SolidWorks.
> You also distribute `ROSMASTER-M3Pro.x_t`. Is that Parasolid file the same
> assembly the URDF was exported from? If so, it would be the authoritative
> source for the dimensions in question 2.
>
> I am happy to cite Yahboom in the resulting publication and to share the
> simulation asset back with you.
>
> Thank you,
> Frank Asante Van Laarhoven
> Doctoral Researcher, Newcastle University
> F.Van-Laarhoven2@newcastle.ac.uk

## Why each question is asked

Each maps to a specific blocker in the apparatus record, so an answer closes
something and a non-answer leaves a named gap rather than a vague one.

| Q | Blocks | If unanswered |
|---|---|---|
| 1 Licence | committing any derived USD to a public repository | asset stays local; the paper cites the vendor file by hash without redistributing it |
| 2 Dimensions | the source-derived collider strategy, which currently assumes primitives | fall back to measuring the STL meshes, recorded as a derived rather than a specified value |
| 3 Camera | the arm4 → optical-frame extrinsic, and the frozen navigation arm pose | measure it physically; the vendor number becomes a cross-check, not the source |
| 4 CAD | whether `.x_t` is an authoritative dimensional source | treat the Parasolid file as unassociated and do not use it |
| 0 Which file | whether our authority decision matches their intent | the decision stands on our own measured evidence; a vendor disagreement would reopen it |

## Rules for the reply, agreed in advance

Fixing these before the answer arrives, so the answer cannot quietly become
stronger evidence than it is.

- A support reply is `VENDOR_STATEMENT`. It is not a measurement and it never
  discharges DT12.
- A licence grant in an email is recorded verbatim with its date and sender, and
  is weaker than a licence file in the distribution. Ask for the latter.
- If Yahboom supplies dimensions that disagree with the meshes, both go in the
  reconciliation table as a recorded discrepancy. Neither silently overwrites
  the other.
- Confirmation of the camera mount does not make the encoded extrinsic a
  measured value.
- `AUTHORITATIVE_ROBOT_DESCRIPTION` is now `M3Pro/urdf/m3pro.urdf`, decided on
  our own measured evidence rather than on a vendor statement. A reply
  confirming it adds corroboration and changes nothing; a reply contradicting it
  is grounds to reopen the decision, recorded as a new dated record rather than
  by editing the existing one.
- A vendor answer about which file is "current" is a statement of intent. It
  does not override what the shipped software measurably loads, and if the two
  disagree that disagreement is itself the finding.
