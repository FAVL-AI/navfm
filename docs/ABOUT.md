# Repository identity: About, description and topics

This file holds the canonical text for the GitHub **About** sidebar and for any
other short description of NavFM. It is version-controlled so the sidebar and the
repository cannot drift apart, and so a change of wording is reviewable like any
other change.

The sidebar itself is repository metadata rather than repository content, and
must be applied through the GitHub API or web UI. The commands are recorded at
the end.

---

## Short description (GitHub About field)

> Evidence-governed reproduction, data-contract validation and simulator
> admissibility for visual robot navigation — GNM/ViNT/NoMaD reproduction and an
> Isaac Sim Yahboom M3 Pro digital twin.

197 characters against GitHub's 350-character limit.

Three properties this wording is chosen for:

- **It names the method, not an aspiration.** *Evidence-governed* is the claim
  the repository can actually support; *state-of-the-art navigation* is not.
- **It names the artefacts.** A reader searching for GNM, ViNT, NoMaD, Isaac Sim
  or the Yahboom M3 Pro finds the repository by the things it contains.
- **It promises nothing about performance.** No accuracy, benchmark or
  sim-to-real improvement is implied, because none is currently demonstrated.

## Topics

```
visual-navigation
reproducibility
embodied-ai
robot-learning
isaac-sim
simulator-validation
measurement-validity
research-evidence
navigation-foundation-models
phd-research
```

`measurement-validity` and `simulator-validation` are deliberate. Most of the
repository's transferable content is about whether an experiment measured what it
claimed to measure, and those terms describe it more honestly than a purely
robotics-flavoured tag set.

## Website

Left empty. To be set to a paper or project page when one exists, rather than to
a placeholder.

---

## One-paragraph description

NavFM is a doctoral research repository studying whether published
visual-navigation systems can be reproduced faithfully, whether newly collected
robot trajectories preserve the data semantics those systems require, and whether
a simulator is physically trustworthy enough to support subsequent experiments.
It targets GNM, ViNT and NoMaD alongside an Isaac Sim digital twin of the Yahboom
ROSMASTER M3 Pro. The contribution is not a navigation architecture but an
evidence trail: fixed data contracts, model-path reproduction, controlled
evaluations, simulator-admissibility tests, negative results, contradictions and
explicit claim boundaries.

## One-page description

A visual-navigation experiment can complete successfully while changing what the
experiment means. A checkpoint may load without all of its parameters executing.
A loss may be finite while optimising the wrong objective. A scene may render
correctly while missing floor collision. A physics query may return a plausible
hit while interrogating the wrong object. A sample may be non-empty and still be
too small, or too biased, to support the claim built on it.

NavFM treats these as research problems rather than implementation details. The
programme establishes a reproducible path from published model release, to
model-ready trajectory data, to physics-valid simulation — and gates each step on
evidence. A claim is admitted only once its measurement is live, causally
relevant to the property asserted, reproducible, and bound to immutable
provenance.

The method has produced results in both directions. Positively: the agreed
Option 1 trajectory format is compatible with all three released model paths,
which complete controlled training-path executions with finite losses and
measurable parameter updates; a frozen ViNT evaluation on 41,872 GO Stanford
pairs has been executed with explicit provenance. Negatively, and more usefully:
roughly 19% of ViNT's released checkpoint elements never execute in the tested
graph; a scene can pass every geometric check while its materials fail to
resolve; a repair verified by the same traversal that caused the defect will
report success while changing nothing; and a probe can name a target it never
physically interrogated.

Those negative results are retained rather than discarded, because several of the
strongest findings arose from measurements that initially appeared to pass. The
repository therefore preserves failed hypotheses, contradictions between evidence
channels, and the amendments that resolved them, so that any later claim can be
traced to the measurement that supports it — and so that a measurement which
turned out to answer the wrong question is visible as such.

---

## Applying the sidebar metadata

The About sidebar is set through the API, which requires a token for the account
that owns the repository. Git operations here authenticate over SSH as `FAVL-AI`;
a `gh` session authenticated as a different account cannot see the repository and
returns 404 on both `GET` and `PATCH`.

```bash
gh auth login --hostname github.com     # as the owning account

gh repo edit FAVL-AI/navfm \
  --description "Evidence-governed reproduction, data-contract validation and simulator admissibility for visual robot navigation — GNM/ViNT/NoMaD reproduction and an Isaac Sim Yahboom M3 Pro digital twin." \
  --add-topic visual-navigation \
  --add-topic reproducibility \
  --add-topic embodied-ai \
  --add-topic robot-learning \
  --add-topic isaac-sim \
  --add-topic simulator-validation \
  --add-topic measurement-validity \
  --add-topic research-evidence \
  --add-topic navigation-foundation-models \
  --add-topic phd-research
```

Equivalently, via the repository page → **About** → gear icon.

## Wording rules

1. The description states what the repository *is*, never what it hopes to
   become.
2. No performance, benchmark or sim-to-real claim appears in metadata that is not
   supported in `README.md` and backed by an artefact under `gates/`.
3. If a claim boundary in `README.md` changes, this file is reviewed in the same
   commit — the sidebar is a claim surface like any other.
4. Superlatives are avoided. The repository's interest is in measurement
   validity, and language that oversells it would undercut exactly that.
