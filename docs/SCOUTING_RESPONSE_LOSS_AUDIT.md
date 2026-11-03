# Scouting mutation response-loss audit

## Isolated V1 implementation candidate — 2026-11-02

Base Draft PR106 `6bad1d4359093294149329333f9b7aa789ebac45`. This candidate is uncommitted and unpublished in a separate detached worktree; it does not change the historical evidence below. Implementation/schema-file preparation was specifically approved; runtime migration, production activation, publication and deployment were not.

- Optional keyed paths for CHECK/CORRECTION/ACTION/RESOLVE reuse existing service decisions. Receipt, planned domain/projection writes and existing audit events commit in one batch. New-key historical correction and case behavior remain unchanged; the earlier proposal to require client expected-case/version is **not implemented**. Existing cross-intent race/recurrence semantics are not repaired by request-key deduplication.
- Same member/farm/operation/key and canonical payload replay the original response; a changed payload conflicts409. Authentication and target farm ownership are checked before replay. A different member has a separate namespace, not access to the original receipt. No extra replay audit event.
- Keyed capability defaults off. It requires exact server opt-in plus explicit positive farm/member limits and prepared receipt/guard tables; no production values are supplied. Missing capability/config/schema returns503, never falls through to unkeyed writes. No runtime DDL is added. Prepared migration0020 and Drizzle definitions are files only.
- Two prepared tables: receipts and a transient CHECK guard. The guard row is inserted/deleted in the same batch for quota rollback; receipts are never automatically deleted. Farm/member row-count quota is synthetic-tested; byte quotas, rate windows, operational values and capacity remain unresolved rollout requirements.
- UI opt-in also defaults false and requires a stable current member ID. The existing application does not supply/activate it. Pending key/body/farm/member stay in memory; explicit same-intent retry only. Once uncertain, a later4xx cannot allow key discard; only matching success or a future authorized reconciliation can resolve uncertainty. No raw payload browser persistence, reload recovery, timer/background delivery or automatic key rotation.
- This conservative candidate has no expiry or410 path. Full response retention is bounded by explicit receipt-count limits, not a time policy. It does not authorize indefinite production storage or safe hard-delete. Retention/privacy and a verified expiry protocol remain separate decisions.
- API adapter: `app/api/_lib/scouting-idempotency.ts`; intent/service orchestration: `application/scouting-intent.ts`; receipt SQL: `infrastructure/scouting-receipt-repository.ts`; write-plan support stays in existing ScoutingRepository. Existing bootstrap sources are unchanged. Existing legacy services keep their behavior; typed validation errors preserve original messages.
- Tests create a fresh synthetic binding and apply fixture SQL only; no product ensureSchema/ensureScoutingRuntime execution. Local official Miniflare integration also exercises the real keyed handler and candidate batch against a new synthetic binding. This is not hosted D1 or live authentication evidence.
- Browser visual/interaction acceptance remains NOT_RUN because the existing access restriction was not retried or bypassed. This is a disabled isolated implementation candidate, not release readiness.

See the worktree ACTIVE_WORK section and external evidence report for exact commands, current counts, independent-review findings and pre-existing type-check failures. The proposals below remain design history rather than authorization to expand this candidate.

Evidence base: `39db0b10750e1b3c3b8122a6717a8a480c3f8ec2`, 2026-10-30. Local investigation only.

## Existing contract and implementation

`PEST_SCOUTING_OPERATIONS_V2.md` §1 requires append-only checks/corrections and actor/time/reason preservation. It does not define mutation request identity, replay duration, or replay response behavior. The idempotency statement in `PEST_SCOUTING_UX_RUNTIME_HARDENING_20260916.md` refers to creating missing runtime tables, not replaying farmer writes.

`ScoutingQueue.post()` sends business fields without a request ID. `sending` disables buttons while the promise is pending, but is cleared on failure. The UI does not automatically retry POSTs. A user retry issues another POST; timestamp defaults are assigned again on the server.

Field-check, correction and action services generate a fresh UUID for each invocation. Their repositories append rows without checking a durable request key. Runtime schema has primary keys on those server-generated IDs, but no caller-operation uniqueness constraint. `(farm_id, location_key)` uniqueness protects location creation only. A correction's `(field_check_id, created_at)` index is non-unique.

## Executed isolated reproduction

Command:

```bash
node --import ./tests/register.mjs --test tests/scouting-response-loss.test.ts
```

PASS 1/1 **characterization**, not an idempotency acceptance pass. The fixture executes real route/service/repository code with in-memory SQLite and foreign keys. It awaits the first successful server response, confirms persistence, discards the response at a simulated client boundary, raises a transport error, then resends the exact same JSON body including the same timestamp. No external request or delivery is allowed.

| Request | First committed write | Same request replay | Result |
| --- | --- | --- | --- |
| Field check | 1 check | 201; new check ID | 2 checks, state version increases twice |
| Correction | 1 correction | 201 | 2 corrections and 2 FIELD_CHECK_CORRECTED events |
| Action | 1 action | 201 | 2 action records |
| Resolve | case closed | 400, no active case | 1 RESOLVED event; client cannot recover the original success response |

Identical state values after replay do not imply a single logical write: counts and provenance history duplicate. This test does not simulate real TCP loss, concurrent requests, deployment D1 behavior, or a new recurrence between the original resolve and its retry.

## Decisions needed before implementation

A durable solution expands the current API and storage contract. No such change is implemented in this audit.

Recommended option: an additive caller-generated operation key, retained by the UI for that operation's retries, with a durable receipt in the same atomic transaction as the domain writes. Scope identity by farm, authenticated member, and operation kind; bind it to a canonical payload hash. Authenticate and authorize every retry before receipt lookup. Return the original resource IDs and result on matching replay; reject reuse with different payload. Retain append-only raw history.

This would affect UI pending-operation state, the four mutation routes, service/repository transaction boundaries, and a schema migration for operation receipts/uniqueness. Field-check append and state projection currently use separate calls and would need atomic coordination with the receipt. A location-only resolve also needs a defined target case/version so a retry cannot be mistaken for a new case's close operation; that scenario remains unexecuted here.

Required choices: key lifetime and retention, payload canonicalization, replay status/body, conflict response, client persistence across refresh, concurrency behavior, and case targeting. Tests must cover simultaneous matching requests, mismatched payload, rollback, crash/restart, later recurrence, and cross-farm/member key isolation.

Alternative: client-only pending/uncertain feedback and reconciliation can reduce accidental replay but cannot guarantee exactly one write across devices, reloads, or lost responses. Deduplicating by timestamp, payload, or an arbitrary time window is unsuitable: legitimate repeated observations/actions may have equal values. In-memory caches are not durable or multi-worker safe.

## Scope and publication

Investigation files: `tests/scouting-response-loss.test.ts`, this document, and only the response-loss section of `ACTIVE_WORK.md`. Production code is unchanged by this investigation. The preceding correction-entry repair owns its own ScoutingQueue/API-test/browser-fixture changes and separate ACTIVE_WORK section. Both remain uncommitted; publication needs their respective approval. Durable idempotency implementation requires a separately approved API/schema scope.

## Proposed V1 contract — design only

### Options and recommendation

| Option | Change | Guarantee / cost |
| --- | --- | --- |
| UI lock and uncertain-result guidance | UI only | Reduces accidental clicks; cannot suppress a committed request replay |
| Client-chosen IDs on existing domain rows | Four domain ID contracts and per-table uniqueness | Cannot uniformly recover action/resolve responses, bind different payloads, or represent a resolve receipt without extra storage |
| One operation-receipt table with an atomic domain write | Additive request metadata, one new table and repository commit boundary | Recommended; durable unique claim, payload conflict detection and original result recovery |
| Durable Object serialization / external queue | New deployment infrastructure | Adds operational scope; a lock alone still needs durable receipts |

Recommend the receipt design for the four manual mutation routes. Existing observation ingestion remains outside the first implementation scope. This is a draft choice, not an approved API/schema change.

### Client intent and compatibility

Generate one random UUID at the first explicit submission; retain it with an immutable payload snapshot through pending, uncertain, and explicit retry states. A deliberate new field observation/action gets a new key even when values match. Editing a payload creates a new intent only after the old uncertain result is reconciled; silently generating a new key on timeout is forbidden. Disable duplicate clicks during pending, but retain the key after timeout/503/invalid response. Do not automatically retry writes.

Proposed optional `Idempotency-Key` header preserves existing request bodies. No-key legacy calls retain current status/body behavior and remain explicitly non-idempotent. The updated UI must always send a key; global safety cannot be claimed while old clients remain. Malformed keyed requests get 422; same scoped key with a different canonical payload gets 409; successful matching replays return the original HTTP status and JSON body (201 for check/correction/action, 200 for resolve). Do not add a synthetic replay event to the domain history.

Add expected target case ID/version for keyed resolve (and any other mutation whose case binding can change while offline). Check the receipt before re-evaluating the already-completed transition, but only after current authorization and target ownership. A new case at the same location must never be closed by the old intent. Old unkeyed requests keep their legacy contract. Target-case/version metadata is a separate additive API decision; resolve is not implementation-ready without it.

### Scope, authorization and payload identity

Unique receipt identity: `(farm_id, authenticated farm_member_id, operation_kind, operation_key_digest)`. Resolve membership from the existing trusted identity path, never from caller role/member headers. Validate `reviewAlerts` and active farm membership on every attempt, including replay. Verify target ownership before returning any receipt; an original check/case remains farm-owned even when no longer active. Revoked membership gets denial, not cached success. A different authorized member has a distinct namespace and does not gain the original receipt. Cross-member retries are not deduplicated and must not be presented as such.

Store a versioned hash of canonical, validated intent: target IDs, expected case/version, evidence/action/reason codes, normalized notes and supported nested detail/secondaryEvidence. Define stable JSON key ordering, numeric rules and omitted/null normalization explicitly; reject unsupported fields in keyed requests or include them in a defined version. Resolve omitted timestamp to an omission marker for hashing and assign the actual timestamp only once at commit; retries with an omitted time must not hash the server's new clock. Persist original generated IDs/time/result. Explicit timestamps remain part of intent. Hash equality is required even after a success exists; the caller never chooses the authoritative hash.

Across deployments, look up the scoped receipt first, then compare using the receipt's stored canonical version and that version's validation/default rules. Keep earlier canonicalizers for the supported replay horizon. An unknown/retired version returns a defined 409 `REPLAY_VERSION_UNSUPPORTED` with reconciliation guidance; it never reexecutes, overwrites the receipt, or silently hashes with today's rules. Validate shared transport limits before lookup, but do not apply new business defaults to an old-version intent. Include rolling-deployment and old-version replay vectors in acceptance checks.

### Minimal schema and atomicity

Minimum recommended storage: one new receipt table, not new columns on every history table. Fields: scoped identity above; `payload_hash` and `canonical_version`; minimal `target_type/target_id` and expected case/version; `http_status`, `response_json`, `committed_at`, `replay_until`, and a compact-expired marker. Composite primary/unique key enforces the claim. Store only bounded, whitelisted successful response DTOs and resource IDs, never raw notes/images/tokens or complete request JSON. This is a schema proposal only; no SQL migration file is created.

Proposed keyed-protocol bounds: lowercase UUIDv4 in canonical 36-byte ASCII form; no arbitrary-length key strings. Limit keyed JSON request body to 16 KiB UTF-8 and serialized cached success response to 4 KiB UTF-8, preserving existing smaller field validation limits. These are proposed new-key-path limits, not changes to legacy acceptance. Reject oversized/invalid input before any write; verify response size before the batch and do not commit an uncachable result. Use strict size limits for nested detail/secondaryEvidence as part of the keyed payload schema.

Per-member and per-farm new-intent rate limits and durable receipt/tombstone storage budgets are mandatory rollout configuration, with values to be chosen from measured usage and available D1 capacity. This decision remains HOLD; no unlimited default is acceptable. Enforce durable storage quota with the same atomic commit so concurrent writers cannot overshoot it. On rate/quota exhaustion, reject only new intents explicitly (proposed 429 with a bounded retry hint); continue authorized existing-receipt lookup/replay. Never evict existing receipts early, silently downgrade to unkeyed writes, or rotate the client's intent key to bypass limits. Tombstone budget exhaustion requires capacity/retention review. Verify key-size, response-size, distributed quota races and sustained unique-key pressure before rollout.

`ScoutingRepository` already accepts a D1Database and uses prepared-statement `batch`. The installed Workers types expose batch/exec and session bookmarks, not an interactive transaction callback. Do not place HTTP waits or JS branching between BEGIN/COMMIT on this binding. The SQLite adapter's explicit transaction in our test is not proof of hosted D1 semantics. The official website returned HTTP 403 in this executor; subsequent direct reading of Cloudflare's official documentation repository established the documented sequential transactional batch/rollback contract. See the source matrix below. The proposed SQL guards, conflict modes and application replay behavior still need executable proof.

Proposed commit sequence, subject to concrete SQL guard/conflict validation:

1. Authenticate, validate and read a matching committed receipt through a primary-consistent path. Matching hash returns original result; mismatch returns 409. An initial miss grants no write authority.
2. Service prepares deterministic candidate IDs/response and a domain mutation plan. Repository builds one batch containing exclusive receipt INSERT, all domain/history/event writes, and final receipt result. Field-check INSERT and projection update must join this batch; they are separate calls today. No committed standalone PENDING receipt is used in V1.
3. Concurrent attempts both may read a miss. Only one exclusive INSERT succeeds. The loser's uniqueness error must abort its entire batch; then it reads the winning committed receipt and compares hash. Do not use `INSERT OR IGNORE` followed by unconditional domain writes. Unknown errors must not be misclassified as duplicate-key success.
4. Case/version preconditions must be checked atomically with the writes. A zero-row conditional UPDATE is not itself rollback: repository design needs a tested SQL guard/abort mechanism so a receipt cannot commit with no domain effect. This guard is an unresolved local implementation proof, not a promise that JS prechecks eliminate the race.
5. Return success only after committed batch confirmation. A worker crash before commit leaves no receipt/effect; after commit, the next matching request recovers the result. If the read cannot establish whether a winner committed, return an uncertain/retryable result; never fall through to a new key or an unguarded write.

No extra business notification delivery is permitted in this transaction. Any already-existing event/outbox writes caused by the operation would join the same guarded commit; replay must not deliver externally or reappend business audit events.

### Failures, retention, privacy and offline intent

Authorization/validation errors do not reserve receipts. Transaction failures roll back both receipt and business effect. A transient 5xx/transport error after an attempted commit remains uncertain; the client retains its original key. Do not cache arbitrary stack traces or permanent negative responses as successful receipts.

Full-response replay duration and privacy retention require an explicit policy choice; no arbitrary number of days is adopted here. After `replay_until`, compact to an expired tombstone preserving scope/key/payload digest and target/result identifiers; return a defined 410 outcome with reconciliation guidance, never execute again under that key. Hard deletion of tombstones would permit old replays, so it requires a separately defined maximum accepted intent age and an enforceable protocol. Never delete domain history as part of receipt expiry. Resource/account erasure and tombstone minimization need their own privacy policy review.

Logs follow `LOGGING_OBSERVABILITY_STANDARD.md` §12: bounded error code, latency, operation kind, replay/conflict/rollback counts and a non-reversible correlation digest; omit raw keys, auth headers, notes, full payloads, PII and cached response JSON. Internal member/farm identifiers in the receipt are access-controlled provenance, not public log data. Keep the key random and unguessable; it is not an authentication credential.

V1 recommendation: retain the immutable pending intent in memory for explicit retries. Optionally persist only key/scope/hash/status metadata for recovery, with account/farm namespacing and clearing on logout; no raw free-text payload in localStorage. A reload with a lost payload must trigger reconciliation, not manufacture a new submission. A read-only receipt-status endpoint or another authorized reconciliation UX is an additional API scope, not assumed to exist. Until specified, cross-reload recovery is incomplete and the UI must disclose that limitation.

Offline background delivery is deferred. Do not replay queues on reconnect under a different account/farm. Later offline support must persist protected payloads, scope them to the original actor, keep original observation time separate from sync time, reauthorize at send, and enforce expected case/version. Expired or stale-case intent requires user review. Retrying after a confirmed denial must never switch identity or auto-issue a new key.

### Layer ownership and verification plan

- API adapter: header/target validation, existing auth/ownership, response serialization and compatibility. No transaction SQL in controller.
- Application service: canonical intent/version, domain preconditions and mutation plan; no UI dependency or SQL.
- Repository/infrastructure: unique claim, primary-consistent receipt read, atomic prepared batch, guard/rollback and receipt serialization storage. No pest decision policy in storage.
- UI: pending intent lifecycle, explicit retries and uncertain-result guidance. Domain evidence enums and scientific meaning remain unchanged.

Required acceptance evidence before claiming safe replay:

1. Same intent sequentially and concurrently through real handlers: one domain row/event and one receipt; original status/IDs/time/body returned on every matching replay.
2. Same key/different payload, including note/timestamp/nested detail differences: 409 and zero additional writes. Stable omission normalization and hash-version vectors.
3. Failure injection after each statement, process crash before/after commit, uniqueness winner/loser, zero-row precondition and primary-read uncertainty: no partial effect or false success.
4. Current role revocation, cross-farm/member key collisions, deleted target and later recurrence: no receipt leak or unintended new-case mutation.
5. Legacy no-key request/response regression; keyed REPLACE/VOID/action/resolve UI tests; timeout/response-loss/manual retry/edited intent; no automatic POST replay.
6. Expiry/tombstone, reload and account switch, no cached PII in logs/browser storage; stored canonical-version replay across deployments; key/body/response byte bounds and atomic per-member/farm rate/storage budgets. Run official local D1/emulator concurrency checks before a separately authorized disposable hosted D1 trial; SQLite-only passes do not establish distributed behavior.

### Staged approval scope

| Stage | Concrete scope | Authority/status |
| --- | --- | --- |
| Current design | This audit plus its ACTIVE_WORK design paragraph | Authorized documentation only; uncommitted |
| Contract and isolated proof | Approve header/target/replay/expiry choices; add local tests/prototype against isolated fixture | Requires follow-up scope; no production activation |
| Local implementation | Four route adapters, service/repository boundaries, UI intent handling, schema definition and one additive migration file, tests/docs | Separate explicit implementation approval; migration creation is not migration execution |
| PR publication | Review exact diff, commit and normal push, CI | Separate approval; not a deployment |
| Disposable hosted proof | Exact isolated D1 target, synthetic records, resource/cost limits | Separate approval; no existing farm DB |
| Runtime rollout | Backup/rollback and retention policy, target DB migration, feature/client rollout and hosting | Separate explicit migration/deployment approval |

This design does not authorize any stage beyond current documentation. Blocking design decisions are target-case semantics, D1 atomic guard proof, replay/retention duration, privacy deletion policy and cross-reload recovery scope. A rollout may begin with keyed requests being optional, but must report legacy no-key replay risk explicitly.

### Review evidence

Advisor skill inspected on 2026-10-30. Executor skill discovery returned no installed skills/launcher root, so required Advisor transport is unavailable; no consultation or Advisor approval is claimed. Root source comparison completed against the referenced files.

Separate read-only document reviewer `idempotency_document_review` found no P1 and two P2 gaps: cross-deployment canonical-version replay and bounded key/receipt resource usage. Both are incorporated above; the reviewer did not run tests or modify files. Its judgment was draft acceptable / implementation readiness HOLD, not hosted D1 or release acceptance. Root accepted both findings. D1 atomic guard, expected-case semantics, replay/retention duration, distributed quota values and reload recovery still require decisions/proof before implementation. The amended wording has root review only; no second independent approval is claimed.

## D1 official-source follow-up — confirmed, inferred, unverified

Read on 2026-10-30. The rendered website returned 403 even on the approved network boundary. The following source pages were read directly from Cloudflare's public [cloudflare-docs repository](https://github.com/cloudflare/cloudflare-docs), branch `production`, under `src/content/docs/d1/`. Observed branch tip after retrieval: `35025d7b360fb1f8573b2f58b2edbb7889200787`. Retrieval used the moving production branch; the tip is provenance context, not an assertion of archived page-byte hashes. The limits FAQ was followed through its `<Render>` to `src/content/partials/d1/faq-limits.mdx`.

| Official page / source path | Confirmed from the source | Boundary |
| --- | --- | --- |
| [D1 Database](https://developers.cloudflare.com/d1/worker-api/d1-database/), `worker-api/d1-database.mdx`, batch/withSession | Statements execute sequentially, non-concurrently; a failing statement aborts/rolls back the entire sequence. Results correspond to statement order. | An atomic batch is documented; application idempotency is not supplied automatically. All related writes must be in that batch. |
| [Limits](https://developers.cloudflare.com/d1/platform/limits/), `platform/limits.mdx` and rendered `faq-limits.mdx` | Individual DB is single-threaded, processes queries one at a time, queues concurrent requests and may return overload when full. | This does not make a JS read-before-write sequence atomic across separate calls, or eliminate queue/timeout uncertainty. |
| [Indexes](https://developers.cloudflare.com/d1/best-practices/use-indexes/), `best-practices/use-indexes.mdx` | UNIQUE indexes enforce uniqueness on one or multiple columns. | Must prove the chosen non-null scope and INSERT actually raise a constraint error; schema choice remains proposed. |
| [Return object](https://developers.cloudflare.com/d1/worker-api/return-object/), `worker-api/return-object.mdx` | `meta.changes`, `changed_db` and result metadata describe effects. | No API is documented here for branching later batch statements in JS based on an earlier statement's changes. Checking results after commit cannot undo an erroneous successful batch. |
| [Debug D1](https://developers.cloudflare.com/d1/observability/debug-d1/), `observability/debug-d1.mdx`, binding timeout behavior | run/all/first/batch accept no per-call timeout or AbortSignal. `Promise.race` limits waiting but does not cancel the query; a timed-out write can still commit. | Timeout is an uncertain result, never evidence of rollback. Keep the original operation key and reconcile before any new intent. |
| [Read replication](https://developers.cloudflare.com/d1/best-practices/read-replication/), `best-practices/read-replication.mdx` | Replication is asynchronous and replicas may be arbitrarily stale; writes go to primary. Sessions/bookmarks provide sequential consistency. Without Sessions API, queries continue to use primary. | Current repository uses the direct DB binding; no claim is made that it currently reads replicas. Future receipt reads must explicitly retain sufficient consistency. |
| [Local development](https://developers.cloudflare.com/d1/best-practices/local-development/), `best-practices/local-development.mdx` | Local development runs a standalone local-only environment, separate from remote data by default. | Local SQL/batch tests cannot establish remote queue timing, network loss, replication lag or deployment recovery behavior. |

**Conditional inference:** for one retained scoped operation key, an exclusive INSERT guarded by a database uniqueness error plus *every* business/history/event/receipt write in a single rollback-capable batch can allow at most one committed effect set. The losing batch must fail entirely and then recover the matching committed receipt. This is an application design inference combining the documented primitives, not a Cloudflare dedicated idempotency guarantee, global exactly-once delivery, or proof of the current code.

**Conflict handling still unverified:** `INSERT OR IGNORE` / `ON CONFLICT DO NOTHING` may turn the first conflict into successful no-op execution; then there is no statement failure to trigger rollback and subsequent unconditional writes could run. The pages above do not establish those SQL conflict-mode details. Test actual candidate SQL on the supported local D1 runtime, including default INSERT error vs ignored conflict, rollback of preceding/following statements, and exact error classification. Do not accept a successful zero-row result as an exclusive claim. The same requirement applies to zero-row version checks and storage quota guards.

**Read/retry refinement:** after a unique collision, or after timeout, perform a fresh receipt read from primary (for example the first statement of a new `withSession('first-primary')` session, subject to adapter verification), or use a bookmark that demonstrably includes the winning commit. An earlier first-primary read does not automatically include a later concurrent commit. A replica miss, a failed read, or a still-pending background write must not trigger an unguarded write, key rotation, or early receipt deletion. Repeated attempts may only use the same key and the full guarded batch. When no outcome can yet be established, report uncertainty and bounded reconciliation; do not report failure as proof of non-commit.

**Concrete HOLD / proof sequence:**

1. Review-only contract choices: expected-case/version targeting, replay/retention/quota values, canonical versions and reload recovery. No infrastructure needed.
2. Separately authorized isolated local implementation/proof: exclusive INSERT vs ignore modes; all-statement rollback; zero-row guard abort; concurrent same-key and payload conflict; size/quota failure. Document runtime versions and command targets. No remote DB or real account.
3. Separately authorized disposable hosted proof, only if remote behavior needs evidence: queue overload, delayed completion after caller timeout, receipt-read consistency, response loss and restart windows. A local pass cannot mark these PASS.
4. Production rollout remains blocked until the above design/proof and operational migration review pass.

### Explicit separation of the next approvals

- **Code/design implementation approval:** exact local UI/route/service/repository/test changes, schema definition and additive migration *file preparation* (if separately included), all using isolated local synthetic fixtures. This does not authorize running that migration on any real DB, creating a remote environment, changing secrets/configuration, or publishing/deploying.
- **PR publication approval:** concrete reviewed commits, ordinary push to existing PR and CI. This does not apply a migration or deploy.
- **Real DB migration approval:** a later request must name the exact database/environment, migration checksum/content, backup/restore/rollback plan, affected tables, capacity/cost, timing and verification. It is distinct from approving code implementation, migration-file creation or CI. No such approval exists in this task.
- **Hosted test / deployment approval:** each needs its own target/resource scope. Creating a disposable remote test DB is also outside the current documentation authorization.

This follow-up changes only this existing design document. No new runtime, remote test environment, migration file, DB action, installation, production code or test execution was performed. Root documentation review and diff checks do not change the previous independent-review or deployment evidence status.
