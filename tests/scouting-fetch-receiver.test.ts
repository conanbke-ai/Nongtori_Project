import assert from 'node:assert/strict';
import {test} from 'node:test';
import {ScoutingHistoryReader, type HistoryLoadState} from '../app/features/pests/presentation/scouting-history-reader';
import {ScoutingOriginalReader, type OriginalState} from '../app/features/pests/presentation/scouting-original-reader';

test('browser-compatible history transport must not receive the reader as its receiver', async()=>{
 let calls=0;
 const read: typeof fetch = async function(this: unknown, input, init){
  assert.equal(this,undefined,'a WebIDL/native fetch must not be invoked as a reader method');calls++;
  assert.equal(init?.method,'GET');assert.equal(init?.cache,'no-store');assert.ok(String(input).includes('farmId=farm-a'));
  return Response.json({location:{id:'loc-a',farm_id:'farm-a'},observations:[],fieldChecks:[],corrections:[],actions:[],alerts:[],caseEvents:[]});
 };
 const states: HistoryLoadState[]=[];
 await new ScoutingHistoryReader(read).load('farm-a','loc-a',state=>states.push(state));
 assert.equal(calls,1);assert.deepEqual(states.map(s=>s.status),['loading','ready']);
});

test('browser-compatible original transport must not receive the reader as its receiver',async()=>{
 let calls=0;
 const read: typeof fetch = async function(this: unknown, input, init){
  assert.equal(this,undefined,'a WebIDL/native fetch must not be invoked as a reader method');calls++;
  assert.equal(init?.method,'GET');assert.equal(init?.cache,'no-store');assert.ok(String(input).includes('fieldCheckId=check-a'));
  return Response.json({original:{id:'check-a',farm_id:'farm-a',location_state_id:'loc-a',primary_evidence_code:'INCONCLUSIVE',checked_at:'2026-11-05T08:00:00Z'}});
 };
 const states: OriginalState[]=[];
 await new ScoutingOriginalReader(read).load('farm-a','loc-a','check-a',state=>states.push(state));
 assert.equal(calls,1);assert.deepEqual(states.map(s=>s.status),['loading','ready']);assert.equal(states.at(-1)?.entry?.id,'check-a');
});
