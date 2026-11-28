// Synthetic read-only binding. Real GET and farm identity queries run, but
// bootstrap and pest aggregate loading are explicitly stubbed. No real DB/DDL.
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { registerHooks } from 'node:module';
import { testIdentityProvider } from './support/test-identity-provider';

let bootstraps = 0;
Object.defineProperty(globalThis, 'memberIdentityBootstrap', { configurable: true, value: () => { bootstraps++; } });
registerHooks({
  resolve(specifier, context, next) {
    if (context.parentURL?.endsWith('/api/farmer-dashboard/route.ts')) {
      if (specifier === '@/db') return { url: 'test:member-bootstrap', shortCircuit: true };
      if (specifier === '@/app/features/pests/application/pest-service') return { url: 'test:member-pests', shortCircuit: true };
    }
    return next(specifier, context);
  },
  load(url, context, next) {
    if (url === 'test:member-bootstrap') return { format: 'module', shortCircuit: true, source: 'export async function ensureSchema(){globalThis.memberIdentityBootstrap();}' };
    if (url === 'test:member-pests') return { format: 'module', shortCircuit: true, source: 'export async function loadPestDashboard(){return {rows:[],totalOpen:0,breakdown:[],pagination:{status:"OPEN",page:1,limit:20,total:0,pageCount:0,openCount:0,doneCount:0}};}' };
    return next(url, context);
  },
});
const { GET } = await import('../app/api/farmer-dashboard/route');

function fixture() {
  let active = true, visible = true;
  const queries: string[] = [];
  const db = { prepare(sql: string) {
    queries.push(sql); let args: unknown[] = [];
    const isIdentity = () => args.some(arg => arg === 'worker-a' || arg === 'farm-a:worker-a');
    return {
      bind(...values: unknown[]) { args = values; return this; },
      async all() {
        if (sql.includes('FROM farms f JOIN farm_members')) return { results: visible && active && isIdentity() ? [{ id: 'farm-a', name: 'SYNTHETIC_A', timezone: 'UTC' }] : [] };
        return { results: [] };
      },
      async first() {
        if (sql.includes('FROM farm_members') && sql.includes("status = 'ACTIVE'")) {
          assert.ok(sql.includes('WHERE farm_id = ?')); assert.equal(args[0], 'farm-a');
          return active && isIdentity() ? { id: 'SYNTHETIC_DB_MEMBER_ID', farm_id: 'farm-a', login_id: 'different-login', identity_subject: 'worker-a', email: null, display_name: 'display-not-id', phone: null, preferred_language: 'ko', role: 'WORKER' } : null;
        }
        return { count: 0 };
      },
    };
  } };
  (globalThis as unknown as { nongtoriTestEnv: unknown }).nongtoriTestEnv = { DB: db };
  return { queries, hide() { visible = false; }, revoke() { active = false; } };
}
test('dashboard exposes only the member ID returned by the actual ACTIVE farm membership resolver', async () => {
  const f = fixture(), before = bootstraps;
  const response = await GET(testIdentityProvider.requestAs('worker-a', '/api/farmer-dashboard?farmId=farm-a'));
  assert.equal(response.status, 200);
  const body = await response.json() as { account: { memberId: string; role: string }; selectedFarm: { id: string } };
  assert.equal(body.account.memberId, 'SYNTHETIC_DB_MEMBER_ID');
  assert.equal(body.account.role, 'WORKER'); assert.equal(body.selectedFarm.id, 'farm-a');
  assert.equal(bootstraps, before + 1, 'only the explicit no-op bootstrap stub was called');
  assert.equal(f.queries.some(sql => /\b(CREATE|INSERT|UPDATE|DELETE|ALTER)\b/i.test(sql)), false);
});
test('no selected farm, inaccessible requested farm and anonymous identity return null member ID', async () => {
  for (const mode of ['unlinked', 'wrong-farm', 'anonymous']) {
    const f = fixture(); if (mode === 'unlinked') f.hide();
    const response = await GET(testIdentityProvider.requestAs(mode === 'anonymous' ? null : 'worker-a', `/api/farmer-dashboard?farmId=${mode === 'wrong-farm' ? 'farm-b' : 'farm-a'}`));
    assert.equal(response.status, 200);
    const body = await response.json() as { account: { memberId: unknown }; selectedFarm: unknown };
    assert.equal(body.account.memberId, null); assert.equal(body.selectedFarm, null);
    assert.equal(f.queries.some(sql => sql.includes('identity_subject IN')), false, 'no unscoped membership fallback');
  }
});
