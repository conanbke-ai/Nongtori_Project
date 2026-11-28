import assert from 'node:assert/strict';
import { test } from 'node:test';
import { dashboardDataState, dashboardSelection } from '../app/lib/dashboard-data-state';

test('a confirmed absent farm cancels the previous farm and item selection', () => {
  assert.deepEqual(dashboardSelection({ farmId: '', itemIds: [], currentItemId: 'old-item' }), { farmId: '', itemId: '' });
  assert.deepEqual(dashboardSelection({ farmId: '', itemIds: ['old-item'], currentItemId: 'old-item' }), { farmId: '', itemId: '' });
});

test('empty items do not revoke a valid farm and valid current selections are preserved', () => {
  assert.deepEqual(dashboardSelection({ farmId: 'farm-a', itemIds: [], currentItemId: 'old-item' }), { farmId: 'farm-a', itemId: '' });
  assert.deepEqual(dashboardSelection({ farmId: 'farm-a', itemIds: ['first', 'second'], currentItemId: 'second' }), { farmId: 'farm-a', itemId: 'second' });
  assert.deepEqual(dashboardSelection({ farmId: 'farm-b', itemIds: ['new-item'], currentItemId: 'old-item' }), { farmId: 'farm-b', itemId: 'new-item' });
});

test('dashboard data state separates unverified, current, refreshing, and stale data', () => {
  assert.equal(dashboardDataState({ hasSuccessfulData: false, loading: true, error: '' }), 'initial-loading');
  assert.equal(dashboardDataState({ hasSuccessfulData: false, loading: false, error: 'load failed' }), 'initial-error');
  assert.equal(dashboardDataState({ hasSuccessfulData: true, loading: false, error: '' }), 'ready');
  assert.equal(dashboardDataState({ hasSuccessfulData: true, loading: true, error: '' }), 'refreshing');
  assert.equal(dashboardDataState({ hasSuccessfulData: true, loading: false, error: 'load failed' }), 'stale');
});
