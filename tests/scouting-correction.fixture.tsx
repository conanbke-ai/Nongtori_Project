// Browser-only fixture. Bundle separately; never import into the application.
import { createRoot } from 'react-dom/client';
import { ScoutingQueue } from '../app/features/pests/presentation/ScoutingQueue';
import '../app/globals.css';
import '../app/features/pests/presentation/scouting.css';

const mode = new URLSearchParams(location.search).get('mode') ?? 'replace';
let checked = false;
let corrected = false;
let correctionAttempts = 0;
let correctionAvailable = false;
const requests: { path: string; body: Record<string, unknown> }[] = [];
const row = {
  id: 'location-a', location_key: 'A-01', display_location: 'A동 1구역', house_code: 'A', bed_code: '1', zone_code: '01',
  current_state: 'FIELD_CHECK_REQUIRED', active_case_id: 'case-a', last_observed_at: '2026-10-30T09:00:00Z',
  last_field_check_at: null, last_action_at: null, last_alert_at: null, last_alert_reason: null,
  primary_issue_code: 'SPIDER_MITE', issue_family: 'PEST', case_status: 'OPEN', latest_humidity: 43,
  latest_leaf_temp: 25, latest_ambient_temp: 24, latest_reference_temp: null, latest_risk_signal: null, observation_count: 1,
};
globalThis.fetch = async (input, init) => {
  const path = String(input);
  if (!init?.method) return Response.json({ rows: checked && !corrected ? [] : [row], counts: {} });
  const body = JSON.parse(String(init.body)) as Record<string, unknown>;
  requests.push({ path, body });
  if (path === '/api/scouting-field-checks') {
    checked = true;
    return Response.json({ fieldCheckId: 'check-a', nextState: 'MONITORING' }, { status: 201 });
  }
  correctionAttempts++;
  if (mode === 'retry' && correctionAttempts === 1) return Response.json({ error: '격리 fixture 저장 실패' }, { status: 503 });
  corrected = true;
  return Response.json({ correctionId: 'correction-a', nextState: 'CONFIRMED' }, { status: 201 });
};
createRoot(document.getElementById('root')!).render(<ScoutingQueue farmId="farm-a" canReview language="ko" />);
const click = (selector: string) => document.querySelector<HTMLButtonElement>(selector)?.click();
async function waitFor(selector: string) {
  for (let attempt = 0; attempt < 100; attempt++) {
    if (document.querySelector(selector)) return;
    await new Promise(resolve => setTimeout(resolve, 20));
  }
  throw new Error(`Missing UI: ${selector}`);
}
async function run() {
  await waitFor('.scouting-location-row');
  click('.scouting-location-row');
  await waitFor('.scouting-detail-actions details:first-child button');
  document.querySelector<HTMLElement>('.scouting-detail-actions details:first-child summary')?.click();
  click('.scouting-detail-actions details:first-child button');
  await waitFor('.scouting-all-clear');
  correctionAvailable = Boolean(document.querySelector('.scouting-correction-panel'));
  if (!correctionAvailable) throw new Error('Correction unavailable after field check left the attention queue');
  if (mode === 'inspect') {
    document.getElementById('qa-report')!.textContent = JSON.stringify({ passed: true, correctionAvailable, requests, overflow: document.documentElement.scrollWidth > innerWidth });
    return;
  }
  click(mode === 'void' ? '.scouting-correction-panel button:last-child' : '.scouting-correction-panel button:nth-child(4)');
  if (mode === 'retry') {
    await waitFor('.review-feedback.error');
    click('.scouting-correction-panel button:nth-child(4)');
  }
  await waitFor('.scouting-location-row');
  const correction = requests.filter(({ path }) => path.includes('corrections'));
  const passed = correctionAvailable && corrected && correction.length === (mode === 'retry' ? 2 : 1)
    && correction.every(({ body }) => body.fieldCheckId === 'check-a' && body.farmId === 'farm-a'
      && body.correctionKind === (mode === 'void' ? 'VOID' : 'REPLACE')
      && body.replacementEvidenceCode === (mode === 'void' ? null : 'DIRECT_MITE_OR_EGG_CONFIRMED')
      && body.reasonCode === 'MISCLICK');
  document.getElementById('qa-report')!.textContent = JSON.stringify({ passed, correctionAvailable, corrected, requests, overflow: document.documentElement.scrollWidth > innerWidth });
}
void run().catch(error => {
  document.getElementById('qa-report')!.textContent = JSON.stringify({ passed: false, error: String(error), requests });
});
