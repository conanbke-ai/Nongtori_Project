import assert from 'node:assert/strict';
import { test } from 'node:test';
import { dashboardDataState } from '../app/lib/dashboard-data-state';

test('dashboard data state separates unverified, current, refreshing, and stale data', () => {
  assert.equal(dashboardDataState({ hasSuccessfulData: false, loading: true, error: '' }), 'initial-loading');
  assert.equal(dashboardDataState({ hasSuccessfulData: false, loading: false, error: 'load failed' }), 'initial-error');
  assert.equal(dashboardDataState({ hasSuccessfulData: true, loading: false, error: '' }), 'ready');
  assert.equal(dashboardDataState({ hasSuccessfulData: true, loading: true, error: '' }), 'refreshing');
  assert.equal(dashboardDataState({ hasSuccessfulData: true, loading: false, error: 'load failed' }), 'stale');
});
