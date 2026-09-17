import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

test('notification center is mounted in the app shell', () => {
  const page = readFileSync('app/page.tsx', 'utf8');
  assert.ok(page.includes("NotificationBridge"));
  assert.ok(page.includes('<FarmerDashboard />'));
  assert.ok(page.includes('<NotificationBridge />'));
});

test('notification bridge deep-links to the scouting case detail', () => {
  const bridge = readFileSync('app/features/notifications/presentation/NotificationBridge.tsx', 'utf8');
  assert.ok(bridge.includes("url.searchParams.set('screen', 'alerts')"));
  assert.ok(bridge.includes("url.searchParams.set('scoutingLocation', locationStateId)"));
  assert.ok(bridge.includes(".farm-select-wrap select"));
});

test('notification recipient state is separate from the underlying case', () => {
  const runtime = readFileSync('db/notification-runtime.ts', 'utf8');
  const api = readFileSync('app/api/notifications/route.ts', 'utf8');
  assert.ok(runtime.includes('app_notifications'));
  assert.ok(runtime.includes('app_notification_recipients'));
  assert.ok(runtime.includes('read_at'));
  assert.ok(runtime.includes('dismissed_at'));
  assert.ok(api.includes('SET read_at = COALESCE(read_at, ?), dismissed_at = ?'));
  assert.ok(!api.includes('DELETE FROM scouting_cases'));
  assert.ok(!api.includes('DELETE FROM scouting_location_states'));
});

test('suppressed scouting observations do not emit app notifications', () => {
  const service = readFileSync('app/features/pests/application/scouting-service.ts', 'utf8');
  assert.ok(service.includes("if (decision.alertDecision !== 'SUPPRESSED')"));
  assert.ok(service.includes('createScoutingAppNotification'));
});
