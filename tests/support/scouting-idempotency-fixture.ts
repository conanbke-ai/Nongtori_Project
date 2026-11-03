// Synthetic new binding only. Never calls product ensureSchema/ensureScoutingRuntime.
import { DatabaseSync } from 'node:sqlite';
import { readFileSync } from 'node:fs';
export function scoutingIntentFixture(withReceipts = true) {
  const sqlite = new DatabaseSync(':memory:');
  sqlite.exec(`PRAGMA foreign_keys=ON;
    CREATE TABLE farms(id TEXT PRIMARY KEY);
    CREATE TABLE houses(id TEXT PRIMARY KEY);
    CREATE TABLE beds(id TEXT PRIMARY KEY);
    CREATE TABLE zones(id TEXT PRIMARY KEY);
    CREATE TABLE capture_sessions(id TEXT PRIMARY KEY);
    CREATE TABLE frames(id TEXT PRIMARY KEY);
    CREATE TABLE frame_predictions(id TEXT PRIMARY KEY);
    CREATE TABLE notification_outbox(id TEXT PRIMARY KEY);
    CREATE TABLE farm_members(id TEXT PRIMARY KEY,farm_id TEXT,login_id TEXT,identity_subject TEXT,
      identity_provider TEXT,email TEXT,display_name TEXT,phone TEXT,preferred_language TEXT,role TEXT,status TEXT);`);
  for (const file of ['0016_pest_scouting_state.sql','0017_pest_scouting_operations_v2.sql',
    ...(withReceipts ? ['0020_scouting_operation_receipts.sql'] : [])]) sqlite.exec(readFileSync(`drizzle/${file}`, 'utf8'));
  sqlite.exec(`INSERT INTO farms VALUES('farm-a'),('farm-b');
    INSERT INTO houses VALUES('house'); INSERT INTO beds VALUES('bed'); INSERT INTO zones VALUES('zone');
    INSERT INTO farm_members VALUES
      ('worker-a','farm-a','worker-a','worker-a','SITES',NULL,'synthetic',NULL,'ko','WORKER','ACTIVE'),
      ('owner-a','farm-a','owner-a','owner-a','SITES',NULL,'synthetic',NULL,'ko','OWNER','ACTIVE'),
      ('owner-b','farm-b','owner-b','owner-b','SITES',NULL,'synthetic',NULL,'ko','OWNER','ACTIVE');
    INSERT INTO scouting_location_states(id,farm_id,house_id,bed_id,zone_id,location_key,house_code,bed_code,zone_code,current_state,active_case_id,created_at,updated_at)
      VALUES('loc','farm-a','house','bed','zone','H:B:Z','H','B','Z','FIELD_CHECK_REQUIRED','case','T','T');
    INSERT INTO scouting_cases(id,farm_id,location_state_id,issue_family,primary_issue_code,status,opened_at,opened_reason,created_at,updated_at)
      VALUES('case','farm-a','loc','PEST','SPIDER_MITE','OPEN','T','SYNTHETIC','T','T');`);
  const observedSql: string[] = [];
  let batchQueue = Promise.resolve();
  let failureIndex: number | null = null, failAfterCommit = false;
  let readFailure: string | null = null;
  function checkRead(sql: string) {
    if (readFailure && sql.includes(readFailure)) { readFailure = null; throw Error('SYNTHETIC_READ_FAILURE'); }
  }
  function prepare(sql: string) {
    let args: (string | number | null)[] = [];
    const statement = {
      sql,
      bind(...values: (string | number | null)[]) { args = values; return statement; },
      async first<T>() { await batchQueue; observedSql.push(sql); checkRead(sql); return (sqlite.prepare(sql).get(...args) as T | undefined) ?? null; },
      async all<T>() { await batchQueue; observedSql.push(sql); checkRead(sql); return { results: sqlite.prepare(sql).all(...args) as T[] }; },
      async run() {
        observedSql.push(sql);
        const r = sqlite.prepare(sql).run(...args); return { success: true, meta: { changes: Number(r.changes) } };
      },
    };return statement;
  }
  const db = { prepare, async batch(statements: ReturnType<typeof prepare>[]) {
    const previous = batchQueue;
    let release!: () => void;
    batchQueue = new Promise<void>(resolve => { release = resolve; });
    await previous;
    observedSql.push('BATCH_BEGIN'); sqlite.exec('BEGIN');
    try {
      const results = [];
      for (let i = 0; i < statements.length; i++) {
        results.push(await statements[i].run());
        if (failureIndex === i) { failureIndex = null; throw Error('SYNTHETIC_BATCH_FAILURE'); }
      }
      sqlite.exec('COMMIT');
      if (failAfterCommit) { failAfterCommit = false; throw Error('SYNTHETIC_COMMIT_RESPONSE_LOSS'); }
      return results;
    } catch (error) { if (sqlite.isTransaction) sqlite.exec('ROLLBACK'); throw error; }
    finally { release(); }
  } } as unknown as D1Database;
  const env = { DB: db, SCOUTING_MUTATION_IDEMPOTENCY: 'true', SCOUTING_RECEIPT_FARM_LIMIT: '100', SCOUTING_RECEIPT_MEMBER_LIMIT: '100' };
  function snapshot() {
    return Object.fromEntries(['scouting_field_checks','scouting_field_check_corrections','scouting_actions',
      'scouting_cases','scouting_location_states','scouting_case_events',
      ...(withReceipts ? ['scouting_operation_receipts','scouting_operation_guards'] : [])]
      .map(table => [table, sqlite.prepare(`SELECT * FROM ${table} ORDER BY rowid`).all()]));
  }
  return { db, sqlite, env, observedSql, snapshot,
    failAt(index: number) { failureIndex = index; }, loseCommitResponse() { failAfterCommit = true; },
    failReadContaining(sql: string) { readFailure = sql; } };
}
