# Nongtori Ripeness Data / Label Backlog

Status: **ACTIVE DESIGN BACKLOG / FIELD POLICY NOT FINAL**
Updated: **2026-09-15**

## Purpose

This backlog manages unresolved data and annotation questions separately from model tuning. The current `KGCV-RIPENESS-V001` mapping remains useful for a development benchmark, but it must not be mistaken for the final Nongtori field-label standard.

## A. Maturity taxonomy

### A1. Final 0–4 maturity definition

Current external-normalization mapping in `LABEL_MAPPING_POLICY.md` is:

- GREEN_SMALL / GREEN → 0
- WHITE → 1
- TURNING_EARLY / TURNING_MID → 2
- TURNING_LATE → 3
- RED_RIPE / OVERRIPE → 4
- FLOWER → null

This is a **normalization mapping for external sources**, not yet a finalized field annotation handbook.

Before field labeling is frozen, define for every stage:

- visual name shown to annotators;
- color / surface-coverage criterion;
- fruit-development criterion;
- allowed ambiguity range;
- examples and counterexamples;
- harvest interpretation kept separate from maturity;
- whether cultivar / lighting conditions alter the decision rule.

### A2. Flower / fruit-set / very-immature handling

Open questions:

- Is a flower outside the maturity task (`null` / NOT_APPLICABLE)?
- Is post-flowering fruit-set before obvious green fruit a maturity-0 sample or a separate state?
- At what minimum fruit-development point does ripeness classification begin?
- Should non-fruit detections be rejected by a preceding detector/state classifier rather than forced into maturity?

Do not silently map flower-like examples to M0 merely because a benchmark source does so.

### A3. M0 ↔ M1 boundary

V008 showed the residual benchmark error is concentrated here, so define this boundary explicitly.

Required policy questions:

- how much green surface still qualifies as M0;
- whether ivory / pale green / white transition belongs to M0 or M1;
- whether fruit size/development is part of the stage decision;
- whether color should be judged on total visible surface or exposed fruit surface only;
- how to treat shadow, white balance, specular highlights, and calyx occlusion.

## B. Annotation handbook

Create a human-readable `RIPENESS_ANNOTATION_GUIDE_V1` only when enough field samples are organized.

Minimum contents:

1. stage table 0–4;
2. representative image set per stage;
3. borderline examples between adjacent stages;
4. NOT_APPLICABLE examples;
5. occlusion / blur / exposure rules;
6. multiple-fruit / partial-fruit crop rules;
7. disagreement / review workflow;
8. version and effective date.

## C. Label adjudication

Do not modify validation/test labels directly after viewing model errors.

Required process:

```text
raw label
→ review flag
→ independent visual review
→ adjudication decision
→ revised label version (if approved)
→ new snapshot version
```

Suggested review statuses:

- `KEEP`
- `AMBIGUOUS`
- `REVIEW_REQUIRED`
- `CORRECTION_PROPOSED`
- `CORRECTION_APPROVED`
- `NOT_APPLICABLE`

Every correction must preserve original label, reviewer, reason, version, and provenance.

## D. Data organization still in progress

Current field/photo/video data are not considered final model-training inventory yet.

Track separately:

- still photos already organized;
- remaining still photos;
- video files and frame extraction;
- frame identity and duplicate control;
- farm / bed / zone identifiers;
- capture angle (front / 45° etc.);
- capture date/time;
- lighting/domain metadata where available;
- source/revision/hash;
- training eligibility.

Do not overwrite or mutate original photos/videos.

## E. Video/frame policy

Before video-derived samples enter a frozen dataset, define:

- extraction cadence or event-based frame selection;
- near-duplicate suppression;
- sequence/group ID to prevent adjacent frames crossing train/valid/test;
- one-fruit tracking identity when feasible;
- label propagation rules;
- uncertain frame exclusion/review rules.

## F. Dataset versioning

`KGCV-RIPENESS-V001` remains a development benchmark.

A successor snapshot must receive a new identity when any material item changes:

- label policy;
- source inventory;
- crop logic;
- review/adjudication result;
- split policy outcome;
- field-data inclusion.

Never silently replace V001 contents while retaining the same snapshot ID.

## G. Model-related items deferred until data/label evidence exists

Do not start these merely to chase score:

- targeted augmentation;
- boundary-aware / structural ordinal loss;
- EfficientNet-specific LR optimization;
- ConvNeXt-Tiny comparison;
- ensemble;
- calibration / TTA.

Move one of these back into an experiment only after this backlog produces a concrete observed problem and experiment hypothesis.

## H. Current immediate priority

1. continue organizing actual photo/video data;
2. preserve V001–V008 as benchmark history;
3. accumulate real boundary examples while organizing data;
4. draft field annotation criteria only when representative samples are sufficient;
5. freeze a new dataset revision;
6. re-run baseline from scratch on the new snapshot.
