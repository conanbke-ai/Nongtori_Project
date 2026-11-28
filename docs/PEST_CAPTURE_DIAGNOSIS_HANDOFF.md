# Pest capture → diagnosis handoff — local candidate

## Approved isolated CI-wiring rehearsal — 2026-11-04

- User explicitly approved isolated application of the4-file candidate plus CI test wiring and local test/build, with original files, actual DB/photos, commit/push/main/deploy excluded. Fresh archive workspace `/workspace/scratch/nongtori-capture-ci-u1E0kH`; original4-file candidate and prior PR108 reconstruction untouched.
- Latest main3547c55 is parent-reported, not available as a local object (`git cat-file -t 3547c55`: Not a valid object name). No callable GitHub connector and prior authentication remains unresolved; no alternate/denied remote access retried. Accordingly this is a known-PR108-content rehearsal, NOT a completed latest-main integration claim.
- Known base tree8595d1a93f6c9d16222ef8ffb80220506910d684 plus approved PR10811 blobs reconstruct expected pre-photo tree `0581e88a92520e3ede008f867454f2578d6ed034`. Git tree hashing was cross-checked against the known baseline, without writing Git objects/index. Parent official connector can compare current main's full SHA/tree to this exact expected tree. Equal tree closes the missing-base evidence without another identical execution; different tree requires relevant delta review.
- Both approved patches applied without conflicts in the isolated known-base archive. `package.json` test:workflows appends only tests/pest-capture-guidance.test.tsx; all previous test entries/order and all other scripts remain unchanged. Existing App workflow already calls that script, so no workflow/deploy/config edit. Scope is now the4-file candidate plus1 package-script file; no remote CI was started.
- First approved workflow execution attempt was allowed and PASS92/92: `NODE_OPTIONS='--import=/workspace/scratch/nongtori-capture-ci-u1E0kH-fetch-guard.mjs' node --run test:workflows`. Log `/workspace/scratch/nongtori-capture-ci-u1E0kH-workflows.tap`; guard disallows real external fetch. These are synthetic bindings, not real farm DB/R2.
- `node --run build` PASS (existing route-classification advisory retained); `node node_modules/typescript/bin/tsc --noEmit --incremental false` and `node --run lint` PASS. Node24.19.0 installed locally versus existing workflow Node22: local evidence is not a remote Node22 run. No package install/server start/model run.
- Current remaining gate: authoritative latest main SHA/tree comparison, then any changed-input validation. Actual browser, live upload/D1, reload recovery/server deduplication and rollout acceptance remain unexecuted. No earlier denial was bypassed; no new execution denial occurred in this attempt. Publication/merge/activation/deployment remain excluded.

## PRECHECK / scope

Goal: implement the missing received → reason → next action handoff for leaf-photo submissions, without pretending that photo acceptance is diagnosis. PROJECT_SCOPE V1 prioritizes field workflows; AI_DECISION_POLICY §6/§8 and FAILURE_EXCEPTION_POLICY §1/§7 require truthful unavailable/unknown states and actionable guidance. The catalog currently declares every target RECORD_ONLY. POST pest-capture already returns sessionId, selected pestCode and UPLOADED_AWAITING_MODEL; the form currently discards those fields.

Known baseline: parent-verified PR108 HEAD8f5eb5bd534111ebe03ceaf3b05391bc1f3f68b1 has the same11 approved blobs as the isolated follow-up. This archive reconstructs known main tree8595d1a93f6c9d16222ef8ffb80220506910d684 plus that approved patch; the remote PR108 commit object is not available here. Remote newer changes remain UNKNOWN.

Risk MEDIUM/HIGH: misleading diagnostic completion, accidental resubmission after post-save refresh error, stale farm feedback. QA roles: Product Flow, Functional/Regression, Reliability and data/provenance review by root; existing independent reviewer may perform read-only review. Browser remains blocked: do not call static markup or deterministic hooks visual acceptance. Advisor runtime unavailable, not consulted.

Acceptance:

1. Only a valid201 receipt matching requested catalog target/session/status is received; selected pest is a filing category, not a diagnosis. Show received status, no diagnosis, optional field-observation next action in4 current languages. No new model, confidence, agronomic threshold or treatment recommendation.
2. Network/malformed/ambiguous response stays uncertain, not falsely failed/successful; no automatic POST retry. Definite existing precommit403/413/422 rejection preserves inputs for correction.
3. A reported post-receipt refresh error does not erase accepted receipt or suggest resubmitting; refresh is read-side work. Existing parent reload internally handles its own errors, so not every hosting/list-refresh error can be detected here.
4. Busy lock blocks duplicate same-context submission; unmount/farm/item changes suppress obsolete callbacks/feedback. No browser payload persistence or server policy change.
5. Zero changes to PR10811 files, original dirty/index, schema/runtime/auth, real data/services or configuration. No commit, new branch, push, merge or deployment. New standalone tests run directly; do not edit PR108 package.json to wire CI while its publication is pending.

## Implemented unit and separation

- `app/components/PestCaptureForm.tsx`: received/rejected/uncertain UI, busy/uncertain ref latch, commit-synchronous farm/item/unmount guard; reset only a confirmed current receipt. Uses existing form controls/styles and4-language result/reason/action copy. No new navigation, automatic prescription or inference.
- `app/features/pests/presentation/pest-capture-submission.ts`: presentation-side HTTP receipt adapter plus bounded user guidance; no repository/domain write or crop threshold. UUID/target/status match required; receipt survives reported read-refresh errors and raw errors are not surfaced.
- `tests/pest-capture-guidance.test.tsx`:6 grouped synthetic tests; every catalog target, malformed/foreign target/status, rejection, callback failure, scope change/unmount, fast duplicate, pre-render unknown latch and static markup. Fake HTTP/hook inputs are explicitly synthetic. Existing pest-records tests separately exercise actual route/SQL against in-memory SQLite and FILES Map; no claim of a new end-to-end browser→DB test.
- This document records scope and evidence rather than editing ACTIVE_WORK/package.json owned by pending PR108. New test is NOT yet in remote CI scripts; direct local execution is explicit. Wire it into existing test:workflows only in a later approved scope after reconciling PR108, not by silently changing its11-file candidate.

## Executed evidence

- Before: actual form callback synthetic test FAIL1/1, received201 followed by refresh throw became error and exposed its raw message. After: PASS. A later fast-repeat test exposed a second defect before React state commit (2 POSTs vs expected1); immediate uncertain ref latch fixes it. `nongtori-capture-guidance-ewIgwr-latch-before.tap` retains that failure.
- Target command: `node --import /workspace/scratch/nongtori-main-integration-check-ol5J5b/no-external-fetch.mjs --import ./tests/register.mjs --test tests/pest-capture-guidance.test.tsx tests/pest-records.test.ts` PASS12/12. TAP `/workspace/scratch/nongtori-capture-guidance-ewIgwr-targeted.tap`.
- Complete existing test:workflows file list plus new guidance test under the same fetch guard: PASS92/92, `/workspace/scratch/nongtori-capture-guidance-ewIgwr-workflows.tap`. Known bootstrap helpers execute only on in-memory test bindings, not on a real database.
- `node node_modules/typescript/bin/tsc --noEmit --incremental false` PASS. Initial new union narrowing error corrected by explicit idle/sending union variants, not any or suppression.
- Changed-file ESLint PASS. `node node_modules/vinext/dist/cli.js build` PASS, `/workspace/scratch/nongtori-capture-guidance-ewIgwr-build.log`; existing static route-classification advisory remains. No browser/server start or deploy.
- Independent read-only reviewer PASS: no new actual P1/P2. Reviewer did not execute tests or independently compare git trees; root checked approved PR10811-file SHA256 equality and all tracked base file comparisons. Only existing file changed is PestCaptureForm; new adapter/test/document make4-file candidate, zero path overlap with PR108.

## Remaining limits and next gate

IMPLEMENTED / synthetic checks PASS / READY_FOR_WORK_QA, not visual or operational acceptance. Existing browser restriction is preserved. No real files, farm data, R2, D1, accounts, model fitting/metrics, environment values or configuration changed. No new branch/commit/push/PR/merge/deployment. Original source/index and PR108 blobs remain unchanged.

The uncertain latch protects only current memory/mount/context. It does not provide server idempotency, safe page reload/reentry recovery, global upload deduplication or a durable capture-status reconciliation service. A successful photo submission does not itself create a diagnostic prediction/attention-list row; optional field guidance refers to existing listed locations. It is not forced verification or treatment. Current parent reload handles its own asynchronous list error internally; refreshFailed only reflects failures the supplied callback actually reports. Languages need field/browser acceptance; static markup is not responsive/keyboard/pixel QA.

Next safe gate: review the4-file local candidate and, after PR108 integration status is known, separately authorize publication plus minimal test-script wiring. Do not enable models or query/apply real DB to make the demonstration appear complete.
