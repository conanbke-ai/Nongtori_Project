import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import path from 'node:path';
import { test } from 'node:test';
import { DatabaseSync } from 'node:sqlite';
import {
  FIXED_TEST_IDENTITIES,
  testIdentityProvider,
  type TestIdentitySubject,
} from './support/test-identity-provider';

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
const communityChat = await import('../app/api/community-chat-messages/route');
const farmAccess = await import('../app/api/_lib/farm-access');
const farmAuth = await import('../app/lib/farm-auth');
const farmChat = await import('../app/api/farm-chat-messages/route');
const farmerDashboard = await import('../app/api/farmer-dashboard/route');
const farmMembers = await import('../app/api/farm-members/route');
const forecastWorker = await import('../app/api/forecast-worker/route');
const fruitAssessments = await import('../app/api/fruit-assessments/route');
const harvestCompletion = await import('../app/api/harvest-completion/route');
const harvestRuns = await import('../app/api/harvest-runs/route');
const miteCapture = await import('../app/api/mite-capture/route');
const notificationWorker = await import('../app/api/notification-worker/route');
const notifications = await import('../app/api/notifications/route');
const observationsRoute = await import('../app/api/observations/route');
const phoneNotifications = await import('../app/api/phone-notifications/route');
const recordNotes = await import('../app/api/record-notes/route');
const scoutingActions = await import('../app/api/scouting-actions/route');
const scoutingFieldCheckCorrections = await import('../app/api/scouting-field-check-corrections/route');
const scoutingFieldChecks = await import('../app/api/scouting-field-checks/route');
const scoutingObservations = await import('../app/api/scouting-observations/route');
const scoutingResolve = await import('../app/api/scouting-resolve/route');
const vendorImport = await import('../app/api/vendor/farm-import/route');
const videoSessions = await import('../app/api/video-sessions/route');
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
for (const identity of Object.values(FIXED_TEST_IDENTITIES)) {
  insert('farm_members', {
    id: identity.subject,
    farm_id: identity.farmId,
    login_id: identity.subject,
    identity_provider: 'SITES',
    identity_subject: identity.subject,
    display_name: identity.displayName,
    role: identity.role,
    status: 'ACTIVE',
    approved_at: stamp,
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
  id: 'item-a', farm_id: 'farm-a', crop_code: 'STRAWBERRY', cultivar_code: 'SEOLHYANG',
  display_name: 'fixture item',
  status: 'ACTIVE', created_at: stamp, updated_at: stamp,
});
insert('forecast_model_registry', {
  id: 'forecast-model-a', model_name: 'fixture-model', model_version: 'v1',
  algorithm: 'FIXTURE_ONLY', status: 'ACTIVE', deployed_at: stamp, created_at: stamp,
});

function authenticatedRequest(
  actor: TestIdentitySubject | null,
  input: string,
  init: RequestInit = {},
) {
  return testIdentityProvider.authenticate(actor, new Request(input, init));
}

function jsonRequest(
  pathname: string,
  method: string,
  actor: TestIdentitySubject | null,
  body: object,
) {
  return testIdentityProvider.requestAs(actor, `/api/${pathname}`, {
    method,
    headers: { 'content-type': 'application/json' },
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

function loopbackRequest(
  pathname: string,
  method = 'GET',
  headers: Record<string, string> = {},
) {
  return new Request(`http://localhost/api/${pathname}`, { method, headers });
}

function uploadRequest(actor: TestIdentitySubject | null) {
  const body = new FormData();
  body.set('farmId', 'farm-a');
  body.set('zoneId', 'zone-a');
  body.set('rgbVideo', new File(['TEST_ONLY'], 'fixture.mp4', { type: 'video/mp4' }));
  return testIdentityProvider.requestAs(actor, '/api/video-upload', { method: 'POST', body });
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

test('authorized member administration updates and deletes one scoped fixture member', async () => {
  const eventsBefore = count('farm_member_events');
  const invited = await farmMembers.POST(jsonRequest('farm-members', 'POST', 'admin-a', {
    farmId: 'farm-a',
    email: 'managed-member@example.test',
    displayName: 'managed member',
    role: 'WORKER',
  }));
  assert.equal(invited.status, 201);
  const memberId = (await invited.json() as { id: string }).id;

  const updated = await farmMembers.PATCH(jsonRequest('farm-members', 'PATCH', 'admin-a', {
    farmId: 'farm-a',
    memberId,
    displayName: 'managed owner',
    role: 'OWNER',
  }));
  assert.equal(updated.status, 200);
  const updatedMember = sqlite.prepare(
    'SELECT display_name, role, status FROM farm_members WHERE id = ?',
  ).get(memberId) as { display_name: string; role: string; status: string };
  assert.equal(updatedMember.display_name, 'managed owner');
  assert.equal(updatedMember.role, 'OWNER');
  assert.equal(updatedMember.status, 'ACTIVE');
  const updatedEvent = sqlite.prepare(`SELECT event_type, actor_member_id, target_member_id
    FROM farm_member_events WHERE event_type = 'MEMBER_UPDATED' AND target_member_id = ?`)
    .get(memberId) as { event_type: string; actor_member_id: string; target_member_id: string };
  assert.equal(updatedEvent.event_type, 'MEMBER_UPDATED');
  assert.equal(updatedEvent.actor_member_id, 'admin-a');
  assert.equal(updatedEvent.target_member_id, memberId);

  insert('notification_outbox', {
    id: 'managed-member-pending-notification',
    farm_id: 'farm-a',
    recipient_member_id: memberId,
    recipient_phone: '01000000000',
    notification_type: 'TEST_ONLY',
    status: 'PENDING',
    created_at: stamp,
  });
  const deleted = await farmMembers.DELETE(authenticatedRequest(
    'admin-a',
    `https://nongtori.test/api/farm-members?farmId=farm-a&memberId=${memberId}`,
    { method: 'DELETE' },
  ));
  assert.equal(deleted.status, 200);
  assert.equal(sqlite.prepare('SELECT id FROM farm_members WHERE id = ?').get(memberId), undefined);
  const canceledNotification = sqlite.prepare(`SELECT status, last_error, recipient_member_id
    FROM notification_outbox WHERE id = 'managed-member-pending-notification'`).get() as {
      status: string;
      last_error: string;
      recipient_member_id: string | null;
    };
  assert.equal(canceledNotification.status, 'CANCELED');
  assert.equal(canceledNotification.last_error, '사용자 계정 삭제로 발송 취소');
  assert.equal(canceledNotification.recipient_member_id, null);
  const deletedEvent = sqlite.prepare(`SELECT event_type, actor_member_id, target_name_snapshot
    FROM farm_member_events WHERE event_type = 'MEMBER_DELETED'
    AND target_name_snapshot = 'managed owner'`).get() as {
      event_type: string;
      actor_member_id: string;
      target_name_snapshot: string;
    };
  assert.equal(deletedEvent.event_type, 'MEMBER_DELETED');
  assert.equal(deletedEvent.actor_member_id, 'admin-a');
  assert.equal(deletedEvent.target_name_snapshot, 'managed owner');
  assert.equal(count('farm_member_events'), eventsBefore + 3);
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
    assert.equal((await forecastWorker.POST(loopbackRequest('forecast-worker', 'POST', {
      authorization: 'Bearer wrong-secret',
    }))).status, 401);
    assert.equal((await harvestCompletion.POST(loopbackRequest('harvest-completion', 'POST', {
      authorization: 'Bearer wrong-secret',
    }))).status, 401);
    assert.equal((await notificationWorker.POST(loopbackRequest('notification-worker', 'POST', {
      authorization: 'Bearer wrong-secret',
    }))).status, 401);
    assert.equal((await vendorImport.POST(loopbackRequest('vendor/farm-import', 'POST', {
      authorization: 'Bearer wrong-secret',
    }))).status, 401);
  } finally {
    globalThis.fetch = originalFetch;
  }
  assert.equal(externalCalls, 0);
  assert.equal(count('farms'), farmCount);
  assert.equal(count('notification_outbox'), outboxCount);
});

test('missing service-token bindings fail closed before writes or external delivery', async () => {
  const bindings = testEnv as unknown as Record<string, unknown>;
  const tokenNames = [
    'FORECAST_WORKER_TOKEN',
    'NOTIFICATION_WORKER_TOKEN',
    'ROBOT_INGEST_TOKEN',
    'VENDOR_IMPORT_TOKEN',
  ];
  const saved = Object.fromEntries(tokenNames.map((name) => [name, bindings[name]]));
  const farmCount = count('farms');
  const harvestCount = count('harvest_runs');
  const outboxCount = count('notification_outbox');
  let externalCalls = 0;
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async () => {
    externalCalls += 1;
    throw new Error('external delivery must not run in authorization tests');
  }) as typeof fetch;
  try {
    for (const name of tokenNames) bindings[name] = undefined;
    assert.equal(
      (await forecastWorker.POST(bearerRequest('forecast-worker', 'POST', 'forecast-secret'))).status,
      401,
    );
    assert.equal(
      (await forecastWorker.PUT(bearerRequest('forecast-worker', 'PUT', 'forecast-secret'))).status,
      401,
    );
    assert.equal(
      (await harvestCompletion.POST(bearerRequest('harvest-completion', 'POST', 'robot-secret'))).status,
      503,
    );
    assert.equal(
      (await notificationWorker.POST(bearerRequest('notification-worker', 'POST', 'notification-secret'))).status,
      401,
    );
    assert.equal(
      (await vendorImport.POST(bearerRequest('vendor/farm-import', 'POST', 'vendor-secret'))).status,
      503,
    );
    assert.equal(
      (await forecastWorker.POST(loopbackRequest('forecast-worker', 'POST', {
        authorization: 'Bearer forecast-secret',
      }))).status,
      401,
    );
    assert.equal(
      (await harvestCompletion.POST(loopbackRequest('harvest-completion', 'POST', {
        authorization: 'Bearer robot-secret',
      }))).status,
      503,
    );
    assert.equal(
      (await notificationWorker.POST(loopbackRequest('notification-worker', 'POST', {
        authorization: 'Bearer notification-secret',
      }))).status,
      401,
    );
    assert.equal(
      (await vendorImport.POST(loopbackRequest('vendor/farm-import', 'POST', {
        authorization: 'Bearer vendor-secret',
      }))).status,
      503,
    );
  } finally {
    for (const name of tokenNames) bindings[name] = saved[name];
    globalThis.fetch = originalFetch;
  }
  assert.equal(externalCalls, 0);
  assert.equal(count('farms'), farmCount);
  assert.equal(count('harvest_runs'), harvestCount);
  assert.equal(count('notification_outbox'), outboxCount);
});

test('loopback URLs require real identity and preserve farm scope', async () => {
  const remoteAnonymous = await farmAccess.getAccessibleFarms(
    new Request('https://nongtori.test/api/farmer-dashboard'),
  );
  assert.deepEqual(remoteAnonymous, []);
  for (const origin of ['http://localhost', 'http://127.0.0.1']) {
    const anonymous = new Request(`${origin}/api/farmer-dashboard`);
    assert.deepEqual(await farmAccess.getAccessibleFarms(anonymous), []);
    assert.equal(await farmAuth.getFarmMember(anonymous, 'farm-a'), null);
  }

  const localOwner = authenticatedRequest(
    'owner-a',
    'http://localhost/api/farmer-dashboard',
  );
  assert.deepEqual((await farmAccess.getAccessibleFarms(localOwner)).map((farm) => farm.id), ['farm-a']);
  assert.equal((await farmAuth.getFarmMember(localOwner, 'farm-a'))?.id, 'owner-a');
  assert.equal(await farmAuth.getFarmMember(localOwner, 'farm-b'), null);

  const dashboardResponse = await farmerDashboard.GET(loopbackRequest('farmer-dashboard'));
  assert.equal(dashboardResponse.status, 200);
  const dashboard = await dashboardResponse.json() as {
    farms: unknown[];
    account: { authenticated: boolean };
    selectedFarm: unknown;
  };
  assert.deepEqual(dashboard.farms, []);
  assert.equal(dashboard.account.authenticated, false);
  assert.equal(dashboard.selectedFarm, null);
});

test('request host and proxy headers never grant farm or worker authorization', async () => {
  const requests = [
    new Request('https://nongtori.test/api/farmer-dashboard', {
      headers: { host: 'localhost' },
    }),
    new Request('https://nongtori.test/api/farmer-dashboard', {
      headers: { 'x-forwarded-host': 'localhost', 'x-forwarded-proto': 'http' },
    }),
    new Request('https://nongtori.test/api/farmer-dashboard', {
      headers: { forwarded: 'for=127.0.0.1;host=localhost;proto=http' },
    }),
    new Request('http://localhost/api/farmer-dashboard', {
      headers: { 'x-forwarded-host': 'nongtori.test', 'x-forwarded-proto': 'https' },
    }),
  ];
  for (const request of requests) {
    assert.deepEqual(await farmAccess.getAccessibleFarms(request), []);
    assert.equal(await farmAuth.getFarmMember(request, 'farm-a'), null);
  }
  assert.equal((await forecastWorker.POST(loopbackRequest('forecast-worker', 'POST'))).status, 401);
  assert.equal((await harvestCompletion.POST(loopbackRequest('harvest-completion', 'POST'))).status, 401);
  assert.equal((await notificationWorker.POST(loopbackRequest('notification-worker', 'POST'))).status, 401);
  assert.equal((await vendorImport.POST(loopbackRequest('vendor/farm-import', 'POST'))).status, 401);
  assert.equal((await forecastWorker.POST(loopbackRequest('forecast-worker', 'POST', {
    authorization: 'Bearer forecast-secret',
  }))).status, 204);
  assert.equal((await notificationWorker.POST(loopbackRequest('notification-worker', 'POST', {
    authorization: 'Bearer notification-secret',
  }))).status, 200);
  assert.equal((await harvestCompletion.POST(loopbackRequest('harvest-completion', 'POST', {
    authorization: 'Bearer robot-secret',
  }))).status, 400);
  assert.equal((await vendorImport.POST(loopbackRequest('vendor/farm-import', 'POST', {
    authorization: 'Bearer vendor-secret',
  }))).status, 400);
});

test('authorization sources do not derive trust from loopback hostnames', () => {
  for (const file of [
    'app/lib/farm-auth.ts',
    'app/api/_lib/farm-access.ts',
    'app/api/_lib/service-token-auth.ts',
    'app/api/farmer-dashboard/route.ts',
    'app/api/forecast-worker/route.ts',
    'app/api/harvest-completion/route.ts',
    'app/api/notification-worker/route.ts',
    'app/api/vendor/farm-import/route.ts',
  ]) {
    const source = readFileSync(file, 'utf8');
    assert.doesNotMatch(source, /localhost|127\.0\.0\.1|isLocalRequest/);
  }
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
  const deleted = await farmChat.DELETE(authenticatedRequest(
    'worker-a',
    `https://nongtori.test/api/farm-chat-messages?farmId=farm-a&messageId=${chatId}`,
    { method: 'DELETE' },
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

test('authorized community and notification routes persist only member-scoped fixture state', async () => {
  let externalCalls = 0;
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async () => {
    externalCalls += 1;
    throw new Error('external delivery must not run in authorization tests');
  }) as typeof fetch;
  try {
    const posted = await communityChat.POST(jsonRequest(
      'community-chat-messages',
      'POST',
      'worker-a',
      { farmId: 'farm-a', content: 'fixture community message', languageHint: 'ko' },
    ));
    assert.equal(posted.status, 201);
    const communityMessageId = (await posted.json() as { row: { id: string } }).row.id;
    assert.equal(
      (sqlite.prepare('SELECT status FROM community_chat_messages WHERE id = ?')
        .get(communityMessageId) as { status: string }).status,
      'ACTIVE',
    );
    const removed = await communityChat.DELETE(authenticatedRequest(
      'worker-a',
      `https://nongtori.test/api/community-chat-messages?farmId=farm-a&messageId=${communityMessageId}`,
      { method: 'DELETE' },
    ));
    assert.equal(removed.status, 200);
    assert.equal(
      (sqlite.prepare('SELECT status FROM community_chat_messages WHERE id = ?')
        .get(communityMessageId) as { status: string }).status,
      'DELETED',
    );

    insert('app_notifications', {
      id: 'member-notification-a',
      farm_id: 'farm-a',
      category: 'SYSTEM',
      notification_type: 'TEST_ONLY',
      severity: 'INFO',
      title: 'fixture notification',
      body: 'fixture notification body',
      created_at: stamp,
    });
    insert('app_notification_recipients', {
      id: 'member-notification-recipient-a',
      notification_id: 'member-notification-a',
      recipient_member_id: 'worker-a',
      created_at: stamp,
    });
    const read = await notifications.POST(jsonRequest('notifications', 'POST', 'worker-a', {
      farmId: 'farm-a', action: 'READ', notificationId: 'member-notification-a',
    }));
    assert.equal(read.status, 200);
    assert.ok((sqlite.prepare(`SELECT read_at FROM app_notification_recipients
      WHERE id = 'member-notification-recipient-a'`).get() as { read_at: string | null }).read_at);

    sqlite.prepare("UPDATE farm_members SET notifications_enabled = 1 WHERE id = 'worker-a'").run();
    const toggled = await phoneNotifications.POST(jsonRequest('phone-notifications', 'POST', 'worker-a', {
      farmId: 'farm-a', action: 'toggle', enabled: false,
    }));
    assert.equal(toggled.status, 200);
    assert.equal(
      (sqlite.prepare("SELECT notifications_enabled FROM farm_members WHERE id = 'worker-a'")
        .get() as { notifications_enabled: number }).notifications_enabled,
      0,
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
  assert.equal(externalCalls, 0);
});

test('authorized media routes use only in-memory object storage and persist fixture records', async () => {
  let externalCalls = 0;
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async () => {
    externalCalls += 1;
    throw new Error('external delivery must not run in authorization tests');
  }) as typeof fetch;
  try {
    const assessmentForm = new FormData();
    assessmentForm.set('farmId', 'farm-a');
    assessmentForm.set('cultivar', 'SEOLHYANG');
    assessmentForm.set('image', new File(['TEST_ONLY'], 'fruit.png', { type: 'image/png' }));
    const assessment = await fruitAssessments.POST(authenticatedRequest(
      'worker-a',
      'https://nongtori.test/api/fruit-assessments',
      { method: 'POST', body: assessmentForm },
    ));
    assert.equal(assessment.status, 201);
    const assessmentId = (await assessment.json() as { assessmentId: string }).assessmentId;
    const assessmentRow = sqlite.prepare(`SELECT object_key, processing_status
      FROM fruit_assessments WHERE id = ?`).get(assessmentId) as {
        object_key: string;
        processing_status: string;
      };
    assert.equal(assessmentRow.processing_status, 'UPLOADED_AWAITING_MODEL');
    assert.equal(storedObjects.has(assessmentRow.object_key), true);

    const observationForm = new FormData();
    for (const [key, value] of [
      ['farmId', 'farm-a'], ['cultivar', 'SEOLHYANG'], ['houseId', 'house-a'],
      ['bedId', 'bed-a'], ['zoneId', 'zone-a'], ['captureMethod', 'PAIRED_STILL'],
      ['pairingId', 'fixture-observation-pair'],
    ]) observationForm.set(key, value);
    observationForm.set('rgb', new File(['RGB_TEST_ONLY'], 'rgb.png', { type: 'image/png' }));
    observationForm.set('thermal', new File(['THERMAL_TEST_ONLY'], 'thermal.tiff', { type: 'image/tiff' }));
    const observation = await observationsRoute.POST(authenticatedRequest(
      'worker-a',
      'https://nongtori.test/api/observations',
      { method: 'POST', body: observationForm },
    ));
    assert.equal(observation.status, 201);
    const observationBody = await observation.json() as { observationId: string; assetCount: number };
    assert.equal(observationBody.assetCount, 2);
    assert.equal(
      (sqlite.prepare('SELECT processing_status FROM observations WHERE id = ?')
        .get(observationBody.observationId) as { processing_status: string }).processing_status,
      'UPLOADED',
    );
    const observationAssets = sqlite.prepare(
      'SELECT object_key FROM assets WHERE observation_id = ?',
    ).all(observationBody.observationId) as { object_key: string }[];
    assert.equal(observationAssets.length, 2);
    assert.equal(observationAssets.every((asset) => storedObjects.has(asset.object_key)), true);

    const miteForm = new FormData();
    miteForm.set('farmId', 'farm-a');
    miteForm.set('itemId', 'item-a');
    miteForm.set('rgbImage', new File(['MITE_TEST_ONLY'], 'mite.png', { type: 'image/png' }));
    const captured = await miteCapture.POST(authenticatedRequest(
      'worker-a',
      'https://nongtori.test/api/mite-capture',
      { method: 'POST', body: miteForm },
    ));
    assert.equal(captured.status, 201);
    const captureSessionId = (await captured.json() as { sessionId: string }).sessionId;
    const capturedSession = sqlite.prepare(`SELECT pest_code, processing_status
      FROM capture_sessions WHERE id = ?`).get(captureSessionId) as {
        pest_code: string;
        processing_status: string;
      };
    assert.equal(capturedSession.pest_code, 'MITE');
    assert.equal(capturedSession.processing_status, 'UPLOADED_AWAITING_MODEL');
    assert.equal(
      (sqlite.prepare('SELECT COUNT(*) AS count FROM inference_runs WHERE capture_session_id = ?')
        .get(captureSessionId) as { count: number }).count,
      0,
    );

    const session = await videoSessions.POST(jsonRequest('video-sessions', 'POST', 'worker-a', {
      farmId: 'farm-a', sourceType: 'PERSONAL_CAPTURE', videos: [],
    }));
    assert.equal(session.status, 201);
    const noteSessionId = (await session.json() as { sessionId: string }).sessionId;
    assert.equal(
      (sqlite.prepare('SELECT processing_status FROM capture_sessions WHERE id = ?')
        .get(noteSessionId) as { processing_status: string }).processing_status,
      'REGISTERED',
    );
    const note = await recordNotes.POST(jsonRequest('record-notes', 'POST', 'worker-a', {
      farmId: 'farm-a', sessionId: noteSessionId, content: 'fixture note for delete', languageHint: 'ko',
    }));
    assert.equal(note.status, 201);
    const noteId = (await note.json() as { id: string }).id;
    const deletedNote = await recordNotes.DELETE(authenticatedRequest(
      'worker-a',
      `https://nongtori.test/api/record-notes?farmId=farm-a&sessionId=${noteSessionId}&noteId=${noteId}`,
      { method: 'DELETE' },
    ));
    assert.equal(deletedNote.status, 200);
    assert.equal(
      (sqlite.prepare('SELECT status FROM mite_record_notes WHERE id = ?').get(noteId) as { status: string }).status,
      'DELETED',
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
  assert.equal(externalCalls, 0);
});

test('authorized harvest run routes persist start and completion state without external work', async () => {
  const started = await harvestRuns.POST(jsonRequest('harvest-runs', 'POST', 'worker-a', {
    farmId: 'farm-a', itemId: 'item-a', note: 'fixture harvest start',
  }));
  assert.equal(started.status, 201);
  const runId = (await started.json() as { id: string }).id;
  const activeRun = sqlite.prepare(`SELECT status, started_by_member_id, note
    FROM harvest_runs WHERE id = ?`).get(runId) as {
      status: string;
      started_by_member_id: string;
      note: string;
    };
  assert.equal(activeRun.status, 'IN_PROGRESS');
  assert.equal(activeRun.started_by_member_id, 'worker-a');
  assert.equal(activeRun.note, 'fixture harvest start');

  const completed = await harvestRuns.PATCH(jsonRequest('harvest-runs', 'PATCH', 'worker-a', {
    farmId: 'farm-a', runId, note: 'fixture harvest complete',
  }));
  assert.equal(completed.status, 200);
  const completedRun = sqlite.prepare(`SELECT status, completed_at, completed_by_member_id, note
    FROM harvest_runs WHERE id = ?`).get(runId) as {
      status: string;
      completed_at: string | null;
      completed_by_member_id: string;
      note: string;
    };
  assert.equal(completedRun.status, 'COMPLETED');
  assert.ok(completedRun.completed_at);
  assert.equal(completedRun.completed_by_member_id, 'worker-a');
  assert.equal(completedRun.note, 'fixture harvest complete');
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
    const claimedJob = await claimed.json() as { job: { id: string } };
    assert.equal(
      (sqlite.prepare("SELECT status FROM forecast_jobs WHERE harvest_run_id = 'authz-run-a'").get() as { status: string }).status,
      'PROCESSING',
    );

    const completedForecast = await forecastWorker.PUT(bearerRequest(
      'forecast-worker',
      'PUT',
      'forecast-secret',
      {
        jobId: claimedJob.job.id,
        harvestRunId: 'authz-run-a',
        targetDate: '2026-10-29',
        horizonDays: 7,
        modelName: 'fixture-model',
        modelVersion: 'v1',
        predictions: [{ gradeCode: 'A', p10: 9000, p50: 10000, p90: 11000 }],
      },
    ));
    assert.equal(completedForecast.status, 200);
    assert.deepEqual(await completedForecast.json(), { harvestRunId: 'authz-run-a', status: 'PRICE_ONLY' });
    assert.equal(
      (sqlite.prepare("SELECT status FROM forecast_jobs WHERE harvest_run_id = 'authz-run-a'").get() as { status: string }).status,
      'COMPLETED',
    );
    assert.equal(
      (sqlite.prepare("SELECT COUNT(*) AS count FROM price_forecasts WHERE model_name = 'fixture-model'").get() as { count: number }).count,
      1,
    );
    assert.equal(
      (sqlite.prepare("SELECT status FROM revenue_forecasts WHERE harvest_run_id = 'authz-run-a'").get() as { status: string }).status,
      'PRICE_ONLY',
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

test('paired video storage failure cleans up delayed sibling puts and permits a clean retry', async () => {
  const originalFiles = testEnv.FILES;
  for (const failedModality of ['THERMAL_VIDEO', 'RGB_VIDEO']) {
    const objects = new Map<string, unknown>();
    let release!: () => void;
    let bothStarted!: () => void;
    const delayed = new Promise<void>(resolve => { release = resolve; });
    const started = new Promise<void>(resolve => { bothStarted = resolve; });
    let puts = 0;
    let fail = true;
    testEnv.FILES = {
      async put(key: string, value: unknown) {
        if (++puts === 2) bothStarted();
        if (fail && key.includes(failedModality)) throw new Error('TEST_ONLY video storage failure');
        if (fail) await delayed;
        objects.set(key, value);
      },
      async delete(key: string) { objects.delete(key); },
    };
    const sessionsBefore = count('capture_sessions');
    const videosBefore = count('video_assets');
    const submit = () => {
      const body = new FormData();
      body.set('farmId', 'farm-a'); body.set('zoneId', 'zone-a'); body.set('itemId', 'item-a');
      body.set('rgbVideo', new File(['RGB_TEST_ONLY'], 'rgb.mp4', { type: 'video/mp4' }));
      body.set('thermalVideo', new File(['THERMAL_TEST_ONLY'], 'thermal.mp4', { type: 'video/mp4' }));
      return videoUpload.POST(authenticatedRequest('worker-a', 'https://nongtori.test/api/video-upload', { method: 'POST', body }));
    };
    try {
      const pending = submit();
      await started;
      await new Promise(resolve => setImmediate(resolve));
      release();
      const failed = await pending;
      assert.equal(failed.status, 400);
      await new Promise(resolve => setImmediate(resolve));
      assert.equal(objects.size, 0, `${failedModality}: late sibling must not survive cleanup`);
      assert.equal(count('capture_sessions'), sessionsBefore);
      assert.equal(count('video_assets'), videosBefore);
      fail = false;
      const retry = await submit();
      assert.equal(retry.status, 201);
      const result = await retry.json() as { sessionId: string; processingStatus: string; pairedModalities: string[] };
      assert.equal(result.processingStatus, 'UPLOADED_AWAITING_FRAME_EXTRACTION');
      assert.deepEqual(result.pairedModalities, ['RGB_VIDEO', 'THERMAL_VIDEO']);
      assert.equal(objects.size, 2);
      assert.equal(count('capture_sessions'), sessionsBefore + 1);
      assert.equal(count('video_assets'), videosBefore + 2);
      const session = sqlite.prepare('SELECT zone_id, processing_status FROM capture_sessions WHERE id = ?').get(result.sessionId);
      assert.equal(session?.zone_id, 'zone-a');
      assert.equal(session?.processing_status, 'UPLOADED_AWAITING_FRAME_EXTRACTION');
      const assets = sqlite.prepare('SELECT object_key FROM video_assets WHERE capture_session_id = ?').all(result.sessionId) as { object_key: string }[];
      assert.equal(assets.length, 2);
      assert.ok(assets.every(asset => objects.has(asset.object_key)));
    } finally { release(); testEnv.FILES = originalFiles; }
  }
});
