import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import path from 'node:path';
import { test } from 'node:test';
import {
  FIXED_TEST_IDENTITIES,
  TestIdentityProvider,
  testIdentityProvider,
} from './support/test-identity-provider';

function appSources() {
  const sources: string[] = [];
  function collect(directory: string) {
    for (const entry of readdirSync(directory, { withFileTypes: true })) {
      const target = path.join(directory, entry.name);
      if (entry.isDirectory()) collect(target);
      else if (/\.(ts|tsx)$/.test(entry.name)) sources.push(readFileSync(target, 'utf8'));
    }
  }
  collect('app');
  return sources;
}

test('fixed identities expose role and farm metadata without granting them in request headers', () => {
  assert.deepEqual(
    Object.values(FIXED_TEST_IDENTITIES).map(({ subject, farmId, role }) => ({ subject, farmId, role })),
    [
      { subject: 'admin-a', farmId: 'farm-a', role: 'ADMIN' },
      { subject: 'owner-a', farmId: 'farm-a', role: 'OWNER' },
      { subject: 'worker-a', farmId: 'farm-a', role: 'WORKER' },
      { subject: 'owner-b', farmId: 'farm-b', role: 'OWNER' },
    ],
  );
  const request = testIdentityProvider.requestAs('worker-a', '/api/farmer-dashboard');
  assert.equal(request.headers.get('oai-authenticated-user-id'), 'worker-a');
  assert.equal(request.headers.has('x-test-role'), false);
  assert.equal(request.headers.has('x-test-farm-id'), false);
});

test('role selection is explicit per request and strips caller-supplied identity headers', () => {
  const spoofed = new Request('https://nongtori.test/api/farmer-dashboard?actor=admin-a', {
    headers: {
      'oai-authenticated-user-id': 'admin-a',
      'oai-authenticated-user-email': 'spoofed@example.test',
    },
  });
  const worker = testIdentityProvider.authenticate('worker-a', spoofed);
  assert.equal(worker.headers.get('oai-authenticated-user-id'), 'worker-a');
  assert.equal(worker.headers.get('oai-authenticated-user-email'), null);
  assert.equal(new URL(worker.url).searchParams.get('actor'), 'admin-a');

  const anonymous = testIdentityProvider.authenticate(null, spoofed);
  assert.equal(anonymous.headers.get('oai-authenticated-user-id'), null);
  assert.equal(anonymous.headers.get('oai-authenticated-user-email'), null);
});

test('provider accepts only relative fixture paths and never becomes a production loader hook', () => {
  assert.throws(
    () => new TestIdentityProvider('https://nongtori.test/path'),
    /must not include a path/,
  );
  assert.throws(
    () => testIdentityProvider.requestAs('admin-a', 'https://example.test/api'),
    /origin-relative pathname/,
  );
  assert.doesNotMatch(readFileSync('tests/register.mjs', 'utf8'), /oai-authenticated-user/);
  for (const source of appSources()) {
    assert.doesNotMatch(source, /test-identity-provider|TestIdentityProvider|FIXED_TEST_IDENTITIES/);
  }
});
