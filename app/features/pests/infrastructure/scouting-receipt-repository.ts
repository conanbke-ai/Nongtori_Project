import type { ReceiptLimits, ReceiptResponse, ReceiptRow, ReceiptScope, ScoutingIntentPersistencePort } from '../application/scouting-intent-persistence-port';
import { ScoutingRepository } from './scouting-repository';

export class ScoutingReceiptRepository implements ScoutingIntentPersistencePort {
  constructor(private db: D1Database) {}

  async schemaAvailable() {
    const result = await this.db.prepare(`SELECT name FROM sqlite_master WHERE type='table'
      AND name IN ('scouting_operation_receipts','scouting_operation_guards')`).all<{ name: string }>();
    return result.results.length === 2;
  }

  async ownsTarget(farmId: string, operation: string, targetId: string) {
    const table = operation === 'CORRECTION' ? 'scouting_field_checks' : 'scouting_location_states';
    return Boolean(await this.db.prepare(`SELECT id FROM ${table} WHERE farm_id=? AND id=?`)
      .bind(farmId, targetId).first());
  }

  find(scope: ReceiptScope) {
    return this.db.prepare(`SELECT canonical_version,payload_hash,http_status,response_json
      FROM scouting_operation_receipts WHERE farm_id=? AND member_id=? AND operation_kind=? AND key_digest=?`)
      .bind(scope.farmId, scope.memberId, scope.operation, scope.keyDigest).first<ReceiptRow>();
  }

  beginMutation(): ReturnType<ScoutingIntentPersistencePort['beginMutation']> {
    const statements: D1PreparedStatement[] = [];
    return {
      repository: new ScoutingRepository(this.db, statements),
      commit: (scope, payloadHash, response, limits) => this.commit(scope, payloadHash, response, statements, limits),
    };
  }

  private async commit(scope: ReceiptScope, payloadHash: string, response: ReceiptResponse,
    statements: D1PreparedStatement[], limits: ReceiptLimits) {
    const guardId = crypto.randomUUID();
    await this.db.batch([
      this.db.prepare(`INSERT INTO scouting_operation_receipts(farm_id,member_id,operation_kind,key_digest,
        canonical_version,payload_hash,http_status,response_json,committed_at) VALUES(?,?,?,?,1,?,?,?,?)`)
        .bind(scope.farmId, scope.memberId, scope.operation, scope.keyDigest,
          payloadHash, response.status, response.json, new Date().toISOString()),
      this.db.prepare(`INSERT INTO scouting_operation_guards(id,accepted) SELECT ?, CASE WHEN
        (SELECT COUNT(*) FROM scouting_operation_receipts WHERE farm_id=?) <= ? AND
        (SELECT COUNT(*) FROM scouting_operation_receipts WHERE farm_id=? AND member_id=?) <= ?
        THEN 1 ELSE 0 END`).bind(guardId, scope.farmId, limits.farm, scope.farmId, scope.memberId, limits.member),
      ...statements,
      this.db.prepare('DELETE FROM scouting_operation_guards WHERE id=?').bind(guardId),
    ]);
  }
}
