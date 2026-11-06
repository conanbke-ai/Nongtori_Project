// Synthetic code inputs only. No DB, identity provider or runtime activation.
import assert from 'node:assert/strict';
import {test} from 'node:test';
import {readFileSync,readdirSync} from 'node:fs';
import path from 'node:path';
import {readLegacyFieldEvidence} from '../app/features/pests/domain/legacy-field-evidence-view';
import {fieldEvidenceCodes} from '../app/features/pests/domain/scouting-policy';

test('legacy view: all eight codes have explicit conservative derived readings, separate from the unmodified source',()=>{
  const expected = [
    ['NO_VISIBLE_EVIDENCE','NONE_VISIBLE',null],
    ['LEAF_DAMAGE_OBSERVED','UNKNOWN',null],
    ['WEBBING_OR_MITE_TRACE_SUSPECTED','UNKNOWN',null],
    ['DIRECT_MITE_OR_EGG_CONFIRMED','PEST','SPIDER_MITE'],
    ['OTHER_PEST_LIKE_EVIDENCE','PEST',null],
    ['DISEASE_LIKE_EVIDENCE','DISEASE',null],
    ['PHYSIOLOGICAL_OR_ENVIRONMENTAL_ABNORMALITY','PHYSIOLOGICAL_ENVIRONMENTAL',null],
    ['INCONCLUSIVE','UNKNOWN',null],
  ];
  assert.deepEqual(expected.map(row=>row[0]),[...fieldEvidenceCodes]);
  for(const [code,family,issueCode]of expected){
    const view=readLegacyFieldEvidence({primaryEvidenceCode:code});
    assert.deepEqual(view.source,{kind:'LEGACY_CODE_INPUT',code});
    assert.deepEqual(view.derived,{kind:'DERIVED_LEGACY_READING',mapperVersion:'LEGACY_FIELD_EVIDENCE_V1',
      status:'RECOGNIZED',findings:[{family,issueCode,certainty:null,severity:null}],definitiveNegative:false});
  }
});

test('legacy view: unknown/non-string codes never infer findings or normalize into a recognized code',()=>{
  for(const code of ['','MITE','APHID','DIRECT_MITE_OR_EGG_CONFIRMED ','no_visible_evidence','__proto__','constructor']){
    const view=readLegacyFieldEvidence({primaryEvidenceCode:code,secondaryEvidence:{issue_code:'SPIDER_MITE'}});
    assert.equal(view.source.code,code);assert.equal(view.derived.status,'UNKNOWN_CODE');
    assert.deepEqual(view.derived.findings,[]);assert.equal(view.derived.definitiveNegative,false);
  }
  for(const code of [null,undefined,0,false,{},['DIRECT_MITE_OR_EGG_CONFIRMED']]){
    const view=readLegacyFieldEvidence({primaryEvidenceCode:code});
    assert.equal(view.source.code,null);assert.equal(view.derived.status,'INVALID_INPUT');assert.deepEqual(view.derived.findings,[]);
  }
});

test('legacy view: secondary JSON and authority metadata are not read, copied or interpreted; frozen input remains unchanged',()=>{
  const input=Object.freeze({primaryEvidenceCode:'INCONCLUSIVE',
    get secondaryEvidence():never{throw Error('OPAQUE_JSON_MUST_NOT_BE_READ');},
    get farmId():never{throw Error('AUTHORITY_MUST_NOT_BE_READ');},
    get permissions():never{throw Error('AUTHORITY_MUST_NOT_BE_READ');},
  });
  const view=readLegacyFieldEvidence(input);
  assert.deepEqual(view.derived.findings,[{family:'UNKNOWN',issueCode:null,certainty:null,severity:null}]);
  assert.deepEqual(Object.keys(view),['source','derived']);
  const plain={primaryEvidenceCode:'OTHER_PEST_LIKE_EVIDENCE',secondaryEvidence:{findings:[{issue_code:'APHID'}],note:'SYNTHETIC_PRIVATE'},memberId:'SYNTHETIC_MEMBER',role:'ADMIN'};
  const snapshot=JSON.stringify(plain),projected=readLegacyFieldEvidence(plain);
  assert.equal(JSON.stringify(plain),snapshot);
  assert.ok(!JSON.stringify(projected).includes('APHID'));assert.ok(!JSON.stringify(projected).includes('SYNTHETIC'));
});

test('legacy view: each output owns its objects and cannot alter future interpretations',()=>{
  const a=readLegacyFieldEvidence({primaryEvidenceCode:'DIRECT_MITE_OR_EGG_CONFIRMED'});
  const b=readLegacyFieldEvidence({primaryEvidenceCode:'DIRECT_MITE_OR_EGG_CONFIRMED'});
  assert.notEqual(a.source,b.source);assert.notEqual(a.derived,b.derived);assert.notEqual(a.derived.findings[0],b.derived.findings[0]);
  const mutable=a.derived.findings[0] as {family:string};mutable.family='UNKNOWN';
  assert.equal(readLegacyFieldEvidence({primaryEvidenceCode:'DIRECT_MITE_OR_EGG_CONFIRMED'}).derived.findings[0].family,'PEST');
});

test('legacy view: pure Domain view has no runtime dependencies and only its allowed read-only presentation consumer',()=>{
  const modulePath='app/features/pests/domain/legacy-field-evidence-view.ts';
  const source=readFileSync(modulePath,'utf8');
  assert.equal(source.split('\n').filter(line=>line.startsWith('import ')).length,1);
  assert.ok(source.startsWith("import type { FieldEvidenceCode }"));
  const consumers:string[]=[];
  function walk(dir:string){for(const entry of readdirSync(dir,{withFileTypes:true})){
    const file=path.join(dir,entry.name);if(entry.isDirectory())walk(file);
    else if(/\.(ts|tsx|mjs)$/.test(file)&&file!==modulePath&&readFileSync(file,'utf8').includes('legacy-field-evidence-view'))consumers.push(file);
  }}walk('app');
  assert.deepEqual(consumers,['app/features/pests/presentation/LegacyEvidenceReading.tsx']);
});
