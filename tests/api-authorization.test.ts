import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import path from 'node:path';
import { test } from 'node:test';
import { DatabaseSync } from 'node:sqlite';

type AuthBoundary =
  | 'FARM_MEMBER'
  | 'FARM_PERMISSION'
  | 'MEMBER_SELF'
  | 'SERVICE_TOKEN';

const mutationContracts: Record<string, AuthBoundary> = {
  'account-profile#PATCH': 'MEMBER_SELF',
  'alert-reviews#POST': 'FARM_PERMISSION',
  'community-chat-messages#DELETE': 'FARM_MEMBER',
  'community-chat-messages#POST': 'FARM_MEMBER',
  'farm-chat-messages#DELETE': 'FARM_MEMBER',
  'farm-chat-messages#POST': 'FARM_MEMBER',
  'farm-members#DELETE': 'FARM_PERMISSION',
  'farm-members#PATCH': 'FARM_PERMISSION',
  'farm-members#POST': 'FARM_PERMISSION',
  'forecast-worker#POST': 'SERVICE_TOKEN',
  'forecast-worker#PUT': 'SERVICE_TOKEN',
  'fruit-assessments#POST': 'FARM_PERMISSION',
  'fruit-weights#POST': 'FARM_PERMISSION',
  'harvest-completion#POST': 'SERVICE_TOKEN',
  'harvest-runs#PATCH': 'FARM_PERMISSION',
  'harvest-runs#POST': 'FARM_PERMISSION',
  'mite-capture#POST': 'FARM_PERMISSION',
  'notification-worker#POST': 'SERVICE_TOKEN',
  'notifications#POST': 'FARM_MEMBER',
  'observations#POST': 'FARM_PERMISSION',
  'pest-capture#POST': 'FARM_PERMISSION',
  'phone-notifications#POST': 'MEMBER_SELF',
  'record-notes#DELETE': 'FARM_MEMBER',
  'record-notes#PATCH': 'FARM_MEMBER',
  'record-notes#POST': 'FARM_MEMBER',
  'scouting-actions#POST': 'FARM_PERMISSION',
  'scouting-field-check-corrections#POST': 'FARM_PERMISSION',
  'scouting-field-checks#POST': 'FARM_PERMISSION',
  'scouting-observations#POST': 'FARM_PERMISSION',
  'scouting-resolve#POST': 'FARM_PERMISSION',
  'vendor/farm-import#POST': 'SERVICE_TOKEN',
  'video-sessions#POST': 'FARM_PERMISSION',
  'video-upload#POST': 'FARM_PERMISSION',
};

function mutationHandlers() {
  const apiRoot = path.resolve('app/api');
  const routeFiles: string[] = [];
  function collect(directory: string) {
    for (const entry of readdirSync(directory, { withFileTypes: true })) {
      const target = path.join(directory, entry.name);
      if (entry.isDirectory()) collect(target);
      else if (entry.name === 'route.ts') routeFiles.push(target);
    }
  }
  collect(apiRoot);
  return routeFiles.flatMap((file) => {
    const route = path.relative(apiRoot, path.dirname(file)).replaceAll(path.sep, '/');
    return [...readFileSync(file, 'utf8').matchAll(/export async function (POST|PUT|PATCH|DELETE)\s*\(/g)]
      .map((match) => `${route}#${match[1]}`);
  }).sort();
}

const sqlite = new DatabaseSync(':memory:');
sqlite.exec('PRAGMA foreign_keys = ON');
for (const file of readdirSync('drizzle').filter((name) => name.endsWith('.sql') && name < '0014').sort()) {
  sqlite.exec(readFileSync(`drizzle/${file}`, 'utf8'));
}

function prepare(sql: string) {
  const statement = () => sqlite.prepare(sql);
  let args: (string | number | null)[] = [];
  return {
    bind(...values: (string | number | null)[]) { args = values; return this; },
    async all<T>() { return { results: statement().all(...args) as T[], success: true, meta: {} }; },
    async first<T>() { return (statement().get(...args) as T | undefined) ?? null; },
    async run() {
      const result = statement().run(...args);
      return { success: true, meta: { changes: Number(result.changes) } };
    },
  };
}

const db = {
  prepare,
  async batch(statements: ReturnType<typeof prepare>[]) {
    sqlite.exec('BEGIN');
    try {
      const results = [];
      for (const statement of statements) results.push(await statement.run());
      sqlite.exec('COMMIT');
      return results;
    } catch (error) {
      sqlite.exec('ROLLBACK');
      throw error;
    }
  },
} as unknown as D1Database;

const storedObjects = new Map<string, unknown>();
const testEnv = {
  DB: db,
  FILES: {
    async put(key: string, value: unknown) { storedObjects.set(key, value); },
    async delete(key: string) { storedObjects.delete(key); },
  },
  FORECAST_WORKER_TOKEN: 'forecast-secret',
  NOTIFICATION_WORKER_TOKEN: 'notification-secret',
  ROBOT_INGEST_TOKEN: 'robot-secret',
  SMS_ALERT_TOKEN: 'sms-secret',
  SMS_ALERT_URL: 'https://sms.invalid.test',
  VENDOR_IMPORT_TOKEN: 'vendor-secret',
};
(globalThis as unknown as { nongtoriTestEnv: unknown }).nongtoriTestEnv = testEnv;

const { ensureSchema } = await import('../db');
await ensureSchema();
for (const file of readdirSync('drizzle').filter((name) => name.endsWith('.sql') && name >= '0014').sort()) {
  sqlite.exec(readFileSync(`drizzle/${file}`, 'utf8'));
}

const accountProfile = await import('../app/api/account-profile/route');
const farmAccess = await import('../app/api/_lib/farm-access');
const farmAuth = await import('../app/lib/farm-auth');
const farmChat = await import('../app/api/farm-chat-messages/route');
const farmMembers = await import('../app/api/farm-members/route');
const forecastWorker = await import('../app/api/forecast-worker/route');
const harvestCompletion = await import('../app/api/harvest-completion/route');
const notificationWorker = await import('../app/api/notification-worker/route');
const scoutingActions = await import('../app/api/scouting-actions/route');
const scoutingFieldCheckCorrections = await import('../app/api/scouting-field-check-corrections/route');
const scoutingFieldChecks = await import('../app/api/scouting-field-checks/route');
const scoutingObservations = await import('../app/api/scouting-observations/route');
const scoutingResolve = await import('../app/api/scouting-resolve/route');
const vendorImport = await import('../app/api/vendor/farm-import/route');
const videoUpload = await import('../app/api/video-upload/route');

const stamp = '2026-10-28T00:00:00.000Z';

function insert(table: string, values: Record<string, string | number | null>) {
  const columns = sqlite.prepare(`PRAGMA table_info(${table})`).all() as {
    name: string;
    notnull: number;
    dflt_value: unknown;
    type: string;
  }[];
  for (const column of columns) {
    if (!(column.name in values) && column.notnull && column.dflt_value === null) {
      values[column.name] = column.type.toUpperCase().includes('INT') ? 0 : 'TEST_ONLY';
    }
  }
  const keys = Object.keys(values);
  sqlite.prepare(
    `INSERT INTO ${table} (${keys.join(',')}) VALUES (${keys.map(() => '?').join(',')})`,
  ).run(...Object.values(values));
}

for (const farmId of ['farm-a', 'farm-b']) {
  insert('farms', {
    id: farmId,
    code: farmId.toUpperCase(),
    name: farmId,
    status: 'ACTIVE',
    created_at: stamp,
    updated_at: stamp,
  });
}
for (const [id, farmId, role] of [
  ['admin-a', 'farm-a', 'ADMIN'],
  ['owner-a', 'farm-a', 'OWNER'],
  ['worker-a', 'farm-a', 'WORKER'],
  ['owner-b', 'farm-b', 'OWNER'],
]) {
  insert('farm_members', {
    id,
    farm_id: farmId,
    login_id: id,
    identity_provider: 'SITES',
    identity_subject: id,
    display_name: id,
    role,
    status: 'ACTIVE',
    created_at: stamp,
    updated_at: stamp,
    joined_at: stamp,
  });
}
insert('houses', {
  id: 'house-a', farm_id: 'farm-a', code: 'H1', name: 'H1', status: 'ACTIVE',
  created_at: stamp, updated_at: stamp,
});
insert('beds', {
  id: 'bed-a', house_id: 'house-a', code: 'B1', name: 'B1', status: 'ACTIVE',
  created_at: stamp, updated_at: stamp,
});
insert('zones', {
  id: 'zone-a', bed_id: 'bed-a', code: 'Z1', name: 'Z1', status: 'ACTIVE',
  created_at: stamp, updated_at: stamp,
});
insert('farm_items', {
  id: 'item-a', farm_id: 'farm-a', crop_code: 'STRAWBERRY', display_name: 'fixture item',
  status: 'ACTIVE', created_at: stamp, updated_at: stamp,
});
insert('forecast_model_registry', {
  id: 'forecast-model-a', model_name: 'fixture-model', model_version: 'v1',
  algorithm: 'FIXTURE_ONLY', status: 'ACTIVE', deployed_at: stamp, created_at: stamp,
});

function jsonRequest(pathname: string, method: string, actor: string | null, body: object) {
  const headers: Record<string, string> = { 'content-type': 'application/json' };
  if (actor) headers['oai-authenticated-user-id'] = actor;
  return new Request(`https://nongtori.test/api/${pathname}`, {
    method,
    headers,
    body: JSON.stringify(body),
  });
}

function bearerRequest(pathname: string, method: string, token = 'wrong-secret', body: object = {}) {
  return new Request(`https://nongtori.test/api/${pathname}`, {
    method,
    headers: { authorization: `Bearer ${token}`, 'content-type': 'application/json' },
    body: JSON.stringify(body),
  });
}

function uploadRequest(actor: string | null) {
  const body = new FormData();
  body.set('farmId', 'farm-a');
  body.set('zoneId', 'zone-a');
  body.set('rgbVideo', new File(['TEST_ONLY'], 'fixture.mp4', { type: 'video/mp4' }));
  const headers: Record<string, string> = {};
  if (actor) headers['oai-authenticated-user-id'] = actor;
  return new Request('https://nongtori.test/api/video-upload', { method: 'POST', headers, body });
}

function count(table: string) {
  return Number((sqlite.prepare(`SELECT COUNT(*) AS count FROM ${table}`).get() as { count: number }).count);
}

test('every mutating API handler is assigned to an explicit authorization boundary', () => {
  assert.deepEqual(Object.keys(mutationContracts).sort(), mutationHandlers());
});

test('member administration rejects unauthenticated, worker, and cross-farm owners without writes', async () => {
  const body = {
    farmId: 'farm-a',
    email: 'new-worker@example.test',
    displayName: 'new worker',
    role: 'WORKER',
  };
  const memberCount = count('farm_members');
  const eventCount = count('farm_member_events');
  for (const actor of [null, 'worker-a', 'owner-b']) {
    const response = await farmMembers.POST(jsonRequest('farm-members', 'POST', actor, body));
    assert.equal(response.status, 403);
  }
  assert.equal(count('farm_members'), memberCount);
  assert.equal(count('farm_member_events'), eventCount);
});

test('profile updates cannot cross farm or run without a member identity', async () => {
  const before = sqlite.prepare("SELECT display_name FROM farm_members WHERE id = 'owner-a'").get() as {
    display_name: string;
  };
  const body = { farmId: 'farm-a', displayName: 'unauthorized change', preferredLanguage: 'ko' };
  for (const actor of [null, 'owner-b']) {
    const response = await accountProfile.PATCH(jsonRequest('account-profile', 'PATCH', actor, body));
    assert.equal(response.status, 404);
  }
  const after = sqlite.prepare("SELECT display_name FROM farm_members WHERE id = 'owner-a'").get() as {
    display_name: string;
  };
  assert.equal(after.display_name, before.display_name);
});

test('video upload denies unauthenticated and cross-farm actors before R2 or session writes', async () => {
  const sessionCount = count('capture_sessions');
  for (const actor of [null, 'owner-b']) {
    const response = await videoUpload.POST(uploadRequest(actor));
    assert.equal(response.status, 403);
  }
  assert.equal(storedObjects.size, 0);
  assert.equal(count('capture_sessions'), sessionCount);
});

test('service workers reject wrong tokens before database mutation or external delivery', async () => {
  const farmCount = count('farms');
  const outboxCount = count('notification_outbox');
  let externalCalls = 0;
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async () => {
    externalCalls += 1;
    throw new Error('external delivery must not run in authorization tests');
  }) as typeof fetch;
  try {
    assert.equal((await forecastWorker.POST(bearerRequest('forecast-worker', 'POST'))).status, 401);
    assert.equal((await forecastWorker.PUT(bearerRequest('forecast-worker', 'PUT'))).status, 401);
    assert.equal((await harvestCompletion.POST(bearerRequest('harvest-completion', 'POST'))).status, 401);
    assert.equal((await notificationWorker.POST(bearerRequest('notification-worker', 'POST'))).status, 401);
    assert.equal((await vendorImport.POST(bearerRequest('vendor/farm-import', 'POST'))).status, 401);
  } finally {
    globalThis.fetch = originalFetch;
  }
  assert.equal(externalCalls, 0);
  assert.equal(count('farms'), farmCount);
  assert.equal(count('notification_outbox'), outboxCount);
});

test('non-local requests require identity while localhost classification stays development-only', async () => {
  assert.equal(farmAccess.isLocalRequest(new Request('http://localhost/api/farmer-dashboard')), true);
  assert.equal(farmAccess.isLocalRequest(new Request('http://127.0.0.1/api/farmer-dashboard')), true);
  assert.equal(farmAccess.isLocalRequest(new Request('https://nongtori.test/api/farmer-dashboard')), false);

  const remoteAnonymous = await farmAccess.getAccessibleFarms(
    new Request('https://nongtori.test/api/farmer-dashboard'),
  );
  assert.deepEqual(remoteAnonymous, []);
  const localFarms = await farmAccess.getAccessibleFarms(
    new Request('http://localhost/api/farmer-dashboard'),
  );
  assert.ok(localFarms.some((farm) => farm.id === 'farm-a'));
  const localMember = await farmAuth.getFarmMember(
    new Request('http://localhost/api/account-profile'),
    'farm-a',
  );
  assert.equal(localMember?.id, 'admin-a');
});

test('authorized user boundaries perform only their scoped fixture writes', async () => {
  const profile = await accountProfile.PATCH(jsonRequest('account-profile', 'PATCH', 'owner-a', {
    farmId: 'farm-a', displayName: 'owner fixture', preferredLanguage: 'vi',
  }));
  assert.equal(profile.status, 200);
  const updatedProfile = sqlite.prepare(
    "SELECT display_name, preferred_language FROM farm_members WHERE id = 'owner-a'",
  ).get() as { display_name: string; preferred_language: string };
  assert.equal(updatedProfile.display_name, 'owner fixture');
  assert.equal(updatedProfile.preferred_language, 'vi');

  const membersBefore = count('farm_members');
  const eventsBefore = count('farm_member_events');
  const invite = await farmMembers.POST(jsonRequest('farm-members', 'POST', 'owner-a', {
    farmId: 'farm-a', email: 'allowed-worker@example.test', displayName: 'allowed worker', role: 'WORKER',
  }));
  assert.equal(invite.status, 201);
  assert.equal(count('farm_members'), membersBefore + 1);
  assert.equal(count('farm_member_events'), eventsBefore + 1);

  const chat = await farmChat.POST(jsonRequest('farm-chat-messages', 'POST', 'worker-a', {
    farmId: 'farm-a', content: 'fixture authorization message', languageHint: 'ko',
  }));
  assert.equal(chat.status, 201);
  const chatId = (await chat.json() as { row: { id: string } }).row.id;
  assert.equal(
    (sqlite.prepare('SELECT status FROM farm_chat_messages WHERE id = ?').get(chatId) as { status: string }).status,
    'ACTIVE',
  );
  const deleted = await farmChat.DELETE(new Request(
    `https://nongtori.test/api/farm-chat-messages?farmId=farm-a&messageId=${chatId}`,
    { method: 'DELETE', headers: { 'oai-authenticated-user-id': 'worker-a' } },
  ));
  assert.equal(deleted.status, 200);
  assert.equal(
    (sqlite.prepare('SELECT status FROM farm_chat_messages WHERE id = ?').get(chatId) as { status: string }).status,
    'DELETED',
  );

  const sessionsBefore = count('capture_sessions');
  const objectsBefore = storedObjects.size;
  const uploaded = await videoUpload.POST(uploadRequest('worker-a'));
  assert.equal(uploaded.status, 201);
  assert.equal(count('capture_sessions'), sessionsBefore + 1);
  assert.equal(storedObjects.size, objectsBefore + 1);
});

test('valid service tokens reach isolated domain work without external delivery', async () => {
  let externalCalls = 0;
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async () => {
    externalCalls += 1;
    throw new Error('external delivery must not run in authorization tests');
  }) as typeof fetch;
  try {
    assert.equal(
      (await forecastWorker.POST(bearerRequest('forecast-worker', 'POST', 'forecast-secret'))).status,
      204,
    );
    const imported = await vendorImport.POST(bearerRequest('vendor/farm-import', 'POST', 'vendor-secret', {
      source: { type: 'CSV_SNAPSHOT', checksum: 'fixture-only' },
      farm: { code: 'AUTHZ_IMPORT', name: 'authorization fixture' },
    }));
    assert.equal(imported.status, 201);
    assert.ok(sqlite.prepare("SELECT id FROM farms WHERE code = 'AUTHZ_IMPORT'").get());

    const harvested = await harvestCompletion.POST(bearerRequest(
      'harvest-completion',
      'POST',
      'robot-secret',
      {
        runId: 'authz-run-a', farmId: 'farm-a', itemId: 'item-a',
        startedAt: '2026-10-28T01:00:00.000Z', completedAt: '2026-10-28T01:05:00.000Z',
        grades: [{ gradeCode: 'A', fruitCount: 2, totalWeightG: 34, averageConfidence: 0.9 }],
      },
    ));
    assert.equal(harvested.status, 202);
    assert.ok(sqlite.prepare("SELECT id FROM harvest_runs WHERE id = 'authz-run-a'").get());
    assert.ok(sqlite.prepare("SELECT id FROM forecast_jobs WHERE harvest_run_id = 'authz-run-a'").get());

    const claimed = await forecastWorker.POST(
      bearerRequest('forecast-worker', 'POST', 'forecast-secret'),
    );
    assert.equal(claimed.status, 200);
    assert.equal(
      (sqlite.prepare("SELECT status FROM forecast_jobs WHERE harvest_run_id = 'authz-run-a'").get() as { status: string }).status,
      'PROCESSING',
    );

    const notification = await notificationWorker.POST(
      bearerRequest('notification-worker', 'POST', 'notification-secret'),
    );
    assert.equal(notification.status, 200);
    assert.deepEqual(await notification.json(), { processed: 0, sent: 0, failed: 0 });
  } finally {
    globalThis.fetch = originalFetch;
  }
  assert.equal(externalCalls, 0);
});

test('authorized scouting routes persist observation, review, correction, action, and resolution', async () => {
  const observationCount = count('scouting_observations');
  const fieldCheckCount = count('scouting_field_checks');
  const correctionCount = count('scouting_field_check_corrections');
  const actionCount = count('scouting_actions');

  const observed = await scoutingObservations.POST(jsonRequest(
    'scouting-observations',
    'POST',
    'admin-a',
    {
      farmId: 'farm-a', houseId: 'house-a', bedId: 'bed-a', zoneId: 'zone-a',
      observedAt: '2026-10-28T03:00:00.000Z', sourceType: 'FUSION',
      issueFamily: 'PEST', issueCode: 'SPIDER_MITE',
      signals: { hasMeaningfulAnomaly: true, hasMeaningfulNewEvidence: true },
      patternFingerprint: 'authz-scouting-route-fixture',
    },
  ));
  assert.equal(observed.status, 201);
  const observation = await observed.json() as {
    observationId: string;
    locationStateId: string;
    caseId: string;
    nextState: string;
  };
  assert.equal(observation.nextState, 'FIELD_CHECK_REQUIRED');
  assert.equal(count('scouting_observations'), observationCount + 1);
  assert.ok(sqlite.prepare(
    'SELECT id FROM scouting_observations WHERE id = ? AND farm_id = ? AND location_state_id = ?',
  ).get(observation.observationId, 'farm-a', observation.locationStateId));

  const checked = await scoutingFieldChecks.POST(jsonRequest(
    'scouting-field-checks',
    'POST',
    'worker-a',
    {
      farmId: 'farm-a', locationStateId: observation.locationStateId,
      observationId: observation.observationId,
      evidenceCode: 'WEBBING_OR_MITE_TRACE_SUSPECTED',
      checkedAt: '2026-10-28T03:05:00.000Z', note: 'fixture field check',
    },
  ));
  assert.equal(checked.status, 201);
  const fieldCheck = await checked.json() as { fieldCheckId: string; nextState: string };
  assert.equal(fieldCheck.nextState, 'SUSPECTED');
  assert.equal(count('scouting_field_checks'), fieldCheckCount + 1);
  const originalEvidence = (sqlite.prepare(
    'SELECT primary_evidence_code FROM scouting_field_checks WHERE id = ?',
  ).get(fieldCheck.fieldCheckId) as { primary_evidence_code: string }).primary_evidence_code;
  assert.equal(originalEvidence, 'WEBBING_OR_MITE_TRACE_SUSPECTED');

  const corrected = await scoutingFieldCheckCorrections.POST(jsonRequest(
    'scouting-field-check-corrections',
    'POST',
    'worker-a',
    {
      farmId: 'farm-a', fieldCheckId: fieldCheck.fieldCheckId, correctionKind: 'REPLACE',
      replacementEvidenceCode: 'DIRECT_MITE_OR_EGG_CONFIRMED', reasonCode: 'MISCLICK',
      correctedAt: '2026-10-28T03:06:00.000Z', note: 'fixture correction',
    },
  ));
  assert.equal(corrected.status, 201);
  const correction = await corrected.json() as { correctionId: string; nextState: string };
  assert.equal(correction.nextState, 'CONFIRMED');
  assert.equal(count('scouting_field_check_corrections'), correctionCount + 1);
  assert.equal(
    (sqlite.prepare('SELECT primary_evidence_code FROM scouting_field_checks WHERE id = ?')
      .get(fieldCheck.fieldCheckId) as { primary_evidence_code: string }).primary_evidence_code,
    originalEvidence,
    'the correction must not rewrite the original field check',
  );

  const acted = await scoutingActions.POST(jsonRequest(
    'scouting-actions',
    'POST',
    'worker-a',
    {
      farmId: 'farm-a', locationStateId: observation.locationStateId,
      actionCode: 'TREATMENT_APPLIED', actionAt: '2026-10-28T03:10:00.000Z',
      note: 'fixture action',
    },
  ));
  assert.equal(acted.status, 201);
  assert.equal((await acted.json() as { nextState: string }).nextState, 'POST_TREATMENT');
  assert.equal(count('scouting_actions'), actionCount + 1);

  const resolved = await scoutingResolve.POST(jsonRequest(
    'scouting-resolve',
    'POST',
    'worker-a',
    {
      farmId: 'farm-a', locationStateId: observation.locationStateId,
      reasonCode: 'TREATMENT_COMPLETED', resolvedAt: '2026-10-28T03:15:00.000Z',
    },
  ));
  assert.equal(resolved.status, 200);
  assert.equal((await resolved.json() as { state: string }).state, 'RESOLVED');
  const closedCase = sqlite.prepare(
    'SELECT status, close_reason FROM scouting_cases WHERE id = ?',
  ).get(observation.caseId) as { status: string; close_reason: string };
  assert.equal(closedCase.status, 'RESOLVED');
  assert.equal(closedCase.close_reason, 'TREATMENT_COMPLETED');
  assert.equal(
    (sqlite.prepare('SELECT current_state FROM scouting_location_states WHERE id = ?')
      .get(observation.locationStateId) as { current_state: string }).current_state,
    'RESOLVED',
  );
});
