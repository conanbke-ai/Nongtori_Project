import assert from 'node:assert/strict';
import { test } from 'node:test';
import { DatabaseSync } from 'node:sqlite';

import {
  resolvePreferredWeight,
  validateWeightObservation,
  weightGrade,
  type WeightObservation,
} from '../app/features/weight/domain/weight-source';

const sqlite = new DatabaseSync(':memory:');
sqlite.exec('PRAGMA foreign_keys = ON');

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

(globalThis as unknown as { nongtoriTestEnv: unknown }).nongtoriTestEnv = {
  DB: db,
  FILES: {
    async put() {},
    async delete() {},
  },
};

const { ensureSchema } = await import('../db');
await ensureSchema();

const { WeightObservationRepository } = await import(
  '../app/features/weight/infrastructure/weight-observation-repository'
);
const {
  appendSensorMeasuredWeight,
  appendVisionEstimatedWeight,
  loadResolvedWeight,
} = await import('../app/features/weight/application/weight-service');
const weightsApi = await import('../app/api/fruit-weights/route');

const stamp = '2026-10-02T00:00:00.000Z';

function insert(table: string, values: Record<string, string | number | null>) {
  const rows = sqlite.prepare(`PRAGMA table_info(${table})`).all() as {
    name: string;
    notnull: number;
    dflt_value: unknown;
    type: string;
  }[];
  for (const column of rows) {
    if (!(column.name in values) && column.notnull && column.dflt_value === null) {
      values[column.name] = column.type.toUpperCase().includes('INT') ? 0 : 'TEST_ONLY';
    }
  }
  const keys = Object.keys(values);
  sqlite.prepare(
    `INSERT INTO ${table} (${keys.join(',')}) VALUES (${keys.map(() => '?').join(',')})`,
  ).run(...Object.values(values));
}

insert('farms', {
  id: 'farm-a',
  code: 'FARM-A',
  name: '테스트 농장',
  status: 'ACTIVE',
  created_at: stamp,
  updated_at: stamp,
});
insert('farm_members', {
  id: 'owner-a',
  farm_id: 'farm-a',
  login_id: 'owner-a',
  identity_provider: 'SITES',
  identity_subject: 'owner-a',
  display_name: 'owner',
  role: 'OWNER',
  status: 'ACTIVE',
  created_at: stamp,
  updated_at: stamp,
});
insert('fruit_assessments', {
  id: 'fruit-a',
  farm_id: 'farm-a',
  cultivar: 'SEOLHYANG',
  source_type: 'PERSONAL_CAPTURE',
  capture_at: stamp,
  object_key: 'test/fruit-a.jpg',
  original_name: 'fruit-a.jpg',
  decision_status: 'MODEL_NOT_VALIDATED',
  processing_status: 'UPLOADED_AWAITING_MODEL',
  created_at: stamp,
});

function request(path: string, method = 'GET', body?: object) {
  return new Request(`https://nongtori.test/api/${path}`, {
    method,
    headers: {
      'oai-authenticated-user-id': 'owner-a',
      ...(body ? { 'content-type': 'application/json' } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });
}

function observation(
  id: string,
  source: WeightObservation['source'],
  weightG: number,
  createdAt: string,
): WeightObservation {
  return {
    id,
    fruitAssessmentId: 'fruit-a',
    source,
    weightG,
    confidence: source === 'VISION_ESTIMATED' ? 0.8 : null,
    modelName: source === 'VISION_ESTIMATED' ? 'rgb-v001' : null,
    modelVersion: source === 'VISION_ESTIMATED' ? 'v001' : null,
    sourceRef: null,
    measuredAt: null,
    createdByMemberId: null,
    createdAt,
  };
}

test('weight grade boundaries remain fixed at 12/16/22g', () => {
  assert.equal(weightGrade(11.999), 'JM_WEIGHT_CANDIDATE');
  assert.equal(weightGrade(12), 'MD_WEIGHT');
  assert.equal(weightGrade(16), 'HI_WEIGHT');
  assert.equal(weightGrade(22), 'SP_WEIGHT');
});

test('measured source priority overrides recency and vision prediction', () => {
  const rows = [
    observation('sensor-old', 'SENSOR_MEASURED', 21.7, '2026-10-01T00:00:00Z'),
    observation('manual-new', 'MANUAL_MEASURED', 22.4, '2026-10-02T00:00:00Z'),
    observation('vision-newest', 'VISION_ESTIMATED', 23.0, '2026-10-03T00:00:00Z'),
  ];
  assert.equal(resolvePreferredWeight(rows)?.id, 'sensor-old');
  assert.equal(weightGrade(resolvePreferredWeight(rows)!.weightG), 'HI_WEIGHT');
});

test('observation validation separates measured and model provenance', () => {
  assert.throws(
    () => validateWeightObservation({
      source: 'VISION_ESTIMATED',
      weightG: 18,
    }),
    /requires model_name and model_version/,
  );
  assert.throws(
    () => validateWeightObservation({
      source: 'MANUAL_MEASURED',
      weightG: 18,
      confidence: 0.9,
    }),
    /cannot carry model metadata or confidence/,
  );
});

test('public API records manual measurement but rejects source spoofing', async () => {
  const spoof = await weightsApi.POST(request('fruit-weights', 'POST', {
    farmId: 'farm-a',
    assessmentId: 'fruit-a',
    weightG: 18.4,
    source: 'SENSOR_MEASURED',
  }));
  assert.equal(spoof.status, 422);

  const saved = await weightsApi.POST(request('fruit-weights', 'POST', {
    farmId: 'farm-a',
    assessmentId: 'fruit-a',
    weightG: 18.4,
    measuredAt: '2026-10-02T01:00:00Z',
  }));
  assert.equal(saved.status, 201);
  const savedJson = await saved.json() as {
    resolved: { source: string; weightG: number; provisionalWeightGrade: string };
  };
  assert.equal(savedJson.resolved.source, 'MANUAL_MEASURED');
  assert.equal(savedJson.resolved.weightG, 18.4);
  assert.equal(savedJson.resolved.provisionalWeightGrade, 'HI_WEIGHT');
});

test('internal sensor observation supersedes manual and vision without deleting history', async () => {
  const repository = new WeightObservationRepository(db);
  await appendVisionEstimatedWeight(repository, {
    farmId: 'farm-a',
    fruitAssessmentId: 'fruit-a',
    weightG: 22.8,
    confidence: 0.81,
    modelName: 'efficientnet-b0',
    modelVersion: 'rgb-v001',
  });
  await appendSensorMeasuredWeight(repository, {
    farmId: 'farm-a',
    fruitAssessmentId: 'fruit-a',
    weightG: 21.6,
    sourceRef: 'harvester:test-load-cell',
    measuredAt: '2026-10-02T01:10:00Z',
  });

  const result = await loadResolvedWeight(repository, 'farm-a', 'fruit-a');
  assert.ok(result);
  assert.equal(result.resolved?.source, 'SENSOR_MEASURED');
  assert.equal(result.resolved?.weightG, 21.6);
  assert.equal(result.resolved?.provisionalWeightGrade, 'HI_WEIGHT');
  assert.equal(result.observations.length, 3);

  const response = await weightsApi.GET(
    request('fruit-weights?farmId=farm-a&assessmentId=fruit-a'),
  );
  assert.equal(response.status, 200);
  const json = await response.json() as {
    resolved: { source: string; weightG: number };
    observations: { source: string }[];
  };
  assert.equal(json.resolved.source, 'SENSOR_MEASURED');
  assert.equal(json.resolved.weightG, 21.6);
  assert.deepEqual(
    json.observations.map((row) => row.source).sort(),
    ['MANUAL_MEASURED', 'SENSOR_MEASURED', 'VISION_ESTIMATED'],
  );
});
