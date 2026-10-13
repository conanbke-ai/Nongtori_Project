# Mite Public Snapshots V001 — Result Freeze

Date: 2026-10-13

## Snapshot roles

The two public sources remain intentionally separate.

### MITE-PUBLIC-FIELD-CONTEXT-V001

- Source: DATA-PEST-001 / Strawberry Dataset
- Role: strawberry-context pest detection development dataset
- Images: 2,844
- Valid bounding boxes: 9,179
- Invalid source boxes excluded from copied snapshot labels: 7
- Source annotations remain read-only and unchanged
- Split: train 1,993 / validation 427 / test 424
- Split policy: preserve audited source split
- Manifest SHA-256: `cd0ad4b7b960d76aad253c1e58033bcd99f6ef349cd495c46114ccb4e484796f`

The seven excluded rows are zero-width YOLO boxes and are not usable detection targets.

### MITE-PUBLIC-MORPHOLOGY-V001

- Source: DATA-PEST-002 / Gent Lab TSSM Detection v2, version 210
- Role: TSSM morphology/life-stage development dataset
- Classes: Adult_female / Immature / Viable_egg
- Images: 1,249
- Bounding boxes: 17,364
- Split: train 854 / validation 203 / test 192
- Manifest SHA-256: `ee85788e80c7874fc0ffd5ac3e0b174990172811b5e8c830d42559abe5013143`

The downloaded source split contained 2 exact cross-split duplicate image hashes and 47 origin-key groups spanning splits. Therefore the source split is not used for Nongtori acceptance. Images connected by either origin key or exact SHA-256 are assigned to one atomic component and deterministically re-split 70/15/15.

## Acceptance boundary

These are public development snapshots. They do not establish Nongtori field readiness.

- public test metrics must not be presented as field acceptance
- actual field data remains an independent acceptance/calibration source
- the two public roles must not be silently merged
- later successor snapshots require new immutable IDs and hashes
