Source: external methodological review
Date received: 2026-08-01
Scope: canonical F13 object-versus-float compatibility measurement specification, its four-row outcome mapping, and the trigger-1 adjudication question
Status: reviewed and dispositioned

---

# F13 Object-versus-Float Compatibility Measurement Specification

## 1. Purpose

Determine whether explicit coercion of GO Stanford trajectory values from the contemporaneous ragged object representation to regular floating-point arrays changes any load-bearing numerical semantics used by the reference evaluation pipeline.

The measurement must distinguish:

1. representation effects;
2. NumPy-version effects;
3. the combined end-to-end difference.

No released checkpoint may be loaded. No model prediction, checkpoint loss, or G0.c performance result may be produced.

## 2. Experimental cells

### Cell A — contemporaneous reference behaviour

* Unmodified reference loader and processing path.
* NumPy 1.23.5.
* Original object-dtype representation.
* No explicit float coercion.
* All warnings retained and counted.

### Cell B — coercion under contemporaneous NumPy

* Same environment and NumPy version as Cell A.
* Same trajectories, samples, order and processing functions.
* Explicit coercion of affected position and yaw values to the proposed floating-point representation.

This cell isolates the representation effect while holding NumPy semantics constant.

### Cell C — canonical compatibility path

* Canonical environment and current NumPy version.
* Same explicit coercion as Cell B.
* Same trajectories, samples, order and processing functions.

This cell measures the difference introduced by the canonical numerical stack after the representation is regularised.

## 3. Required contrasts

### Representation effect

[
B-A
]

This determines whether coercion itself changes any computed value under fixed NumPy semantics.

### NumPy-version effect

[
C-B
]

This determines whether the NumPy/environment transition changes values after coercion.

### End-to-end compatibility difference

[
C-A
]

This determines the total difference between contemporaneous reference behaviour and the proposed canonical compatibility path.

## 4. Measurement population

The comparison must cover the complete declared G0.c holdout unless technically impossible.

For every valid sample or timestep, compare every load-bearing value affected directly or indirectly by the representation, including:

* source position;
* source yaw;
* goal position;
* relative position;
* distance;
* sine/cosine orientation values;
* action labels;
* distance labels;
* masks;
* any deterministic intermediate entering an implemented G0.c loss.

The report must state:

* number of trajectories;
* number of valid samples;
* number of compared fields or arrays;
* excluded samples, if any;
* the reason for every exclusion.

## 5. Equality reporting

For every compared field, report:

* shape;
* dtype;
* bitwise or exact equality;
* maximum absolute difference;
* maximum relative difference where defined;
* count of unequal values;
* count of non-finite values;
* first differing trajectory and sample;
* warning count;
* exception count.

Bit identity and tolerance equality must be reported separately.

A tolerance-equivalent result must not be described as bit-identical.

## 6. Outcome mapping

| Result                                                                                                                                                                                                                                     | Required interpretation                                                                                                                                                                                                                                   |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **B−A, C−B and C−A are bit-identical for every load-bearing value.**                                                                                                                                                                       | **Literal compatibility restoration.** Explicit coercion removes the deprecated representation while reproducing the contemporaneous reference computation exactly.                                                                                       |
| **B−A is bit-identical, while C−B or C−A differs only within the declared floating-point tolerance, with no material change to sample membership, labels, masks, implemented losses, behavioural orderings or classificatory quantities.** | **Numerical-semantics-preserving compatibility adaptation, not literal era restoration.** Coercion itself has zero measured numerical effect; the canonical numerical stack introduces only bounded floating-point differences.                           |
| **B−A is not bit-identical but remains within the declared tolerance, with no material change to sample membership, labels, masks, implemented losses, behavioural orderings or classificatory quantities.**                               | **Representation-changing compatibility adaptation.** Coercion creates a third numerical behaviour distinct from the contemporaneous object representation, although downstream semantics remain tolerance-equivalent. It must not be called restoration. |
| **Any comparison changes sample membership, a label, mask, finite/non-finite status, implemented loss materially, behavioural ordering or another classificatory quantity beyond the declared tolerance.**                                 | **Semantic intervention.** The proposed coercion changes the evaluation instrument and requires a separately preregistered protocol amendment before use.                                                                                                 |

## 7. Warning interpretation

Warning behaviour is recorded independently of numerical equivalence.

If Cell A succeeds only while emitting `VisibleDeprecationWarning`, record:

> The released reference corpus was processable under the contemporaneous NumPy dependency semantics, but the reference path relied uniformly on deprecated ragged-array behaviour that later NumPy releases converted into an error.

The warning does not establish numerical invalidity. It establishes dependency fragility and reliance on behaviour already marked for removal.

## 8. Serialization procedure

Each cell must produce a machine-readable intermediate archive before cross-cell comparison.

For every valid sample, serialize a canonical record containing at least:

* trajectory identifier;
* timestep or sample index;
* observation index;
* goal index;
* source position;
* source yaw;
* goal position;
* relative position;
* distance;
* orientation representation;
* action label;
* distance label;
* masks;
* field dtypes;
* field shapes.

Floating-point values must be stored in an explicitly lossless binary format, such as NumPy `.npz`. Human-readable summaries may supplement but must not replace the binary archive.

Each cell archive must record:

* repository commit;
* upstream commit;
* comparison-script commit;
* environment identity;
* Python version;
* NumPy version;
* corpus digest;
* split digest;
* trajectory count;
* sample count;
* warning count;
* archive SHA-256.

## 9. Comparison procedure

The comparison process must:

1. verify identical corpus and split identities across cells;
2. verify identical trajectory and sample keys;
3. require one-to-one sample correspondence;
4. refuse comparison if any required sample is missing;
5. compare serialized fields rather than rerunning preprocessing during comparison;
6. report bit identity and numerical differences separately;
7. emit both machine-readable and human-readable results;
8. preserve the original cell archives unchanged.

## 10. Trigger-1 adjudication question

The red-team must answer:

> Does the proposed coercion preserve all load-bearing numerical semantics, or does it create a third evaluation behaviour distinct from both the contemporaneous reference environment and the current failing environment?

The verdict must be one of:

* **Fixing**
* **Rescuing**
* **Cannot determine**

The compatibility patch may be applied to the registered G0.c path only after a **Fixing** verdict.
