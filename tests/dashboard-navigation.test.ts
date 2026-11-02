import assert from 'node:assert/strict';
import { test } from 'node:test';
import {
  dashboardScreenFromSearch,
  writeDashboardScreen,
} from '../app/lib/dashboard-navigation';

test('dashboard screen parsing accepts direct links and rejects unknown screens', () => {
  assert.equal(dashboardScreenFromSearch('?screen=alerts'), 'alerts');
  assert.equal(dashboardScreenFromSearch('?farmId=farm-a&screen=account'), 'account');
  assert.equal(dashboardScreenFromSearch('?screen=unknown'), null);
  assert.equal(dashboardScreenFromSearch('?farmId=farm-a'), null);
});

test('explicit dashboard navigation pushes once and preserves unrelated URL state', () => {
  const calls: { method: string; url: string }[] = [];
  const history = {
    pushState(_data: unknown, _unused: string, url?: string | URL | null) {
      calls.push({ method: 'push', url: String(url) });
    },
    replaceState(_data: unknown, _unused: string, url?: string | URL | null) {
      calls.push({ method: 'replace', url: String(url) });
    },
  };

  assert.equal(writeDashboardScreen({
    currentScreen: 'home',
    nextScreen: 'capture',
    href: 'https://nongtori.example/?screen=home&farmId=farm-a#today',
    history,
  }), true);
  assert.deepEqual(calls, [{
    method: 'push',
    url: 'https://nongtori.example/?screen=capture&farmId=farm-a#today',
  }]);

  assert.equal(writeDashboardScreen({
    currentScreen: 'capture',
    nextScreen: 'capture',
    href: calls[0].url,
    history,
  }), false);
  assert.equal(calls.length, 1, 'same-screen clicks must not add duplicate history entries');
});

test('initial fallback normalization replaces instead of pushing', () => {
  const calls: { method: string; url: string }[] = [];
  const history = {
    pushState(_data: unknown, _unused: string, url?: string | URL | null) {
      calls.push({ method: 'push', url: String(url) });
    },
    replaceState(_data: unknown, _unused: string, url?: string | URL | null) {
      calls.push({ method: 'replace', url: String(url) });
    },
  };

  assert.equal(writeDashboardScreen({
    currentScreen: 'home',
    nextScreen: 'home',
    href: 'https://nongtori.example/?screen=unknown&farmId=farm-a#today',
    history,
    mode: 'replace',
  }), true);
  assert.deepEqual(calls, [{
    method: 'replace',
    url: 'https://nongtori.example/?screen=home&farmId=farm-a#today',
  }]);
});
