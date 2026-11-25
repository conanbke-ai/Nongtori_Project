import type { ScoutingRepositoryPort } from './scouting-repository-port';

export type ReceiptScope = { farmId: string; memberId: string; operation: string; keyDigest: string };
export type ReceiptRow = { canonical_version: number; payload_hash: string; http_status: number; response_json: string };
export type ReceiptResponse = { status: number; json: string };
export type ReceiptLimits = { farm: number; member: number };

export interface ScoutingReceiptReaderPort {
  schemaAvailable(): Promise<boolean>;
  ownsTarget(farmId: string, operation: string, targetId: string): Promise<boolean>;
  find(scope: ReceiptScope): Promise<ReceiptRow | null>;
}

export interface ScoutingIntentPersistencePort extends ScoutingReceiptReaderPort {
  beginMutation(): {
    repository: ScoutingRepositoryPort;
    commit(scope: ReceiptScope, payloadHash: string, response: ReceiptResponse, limits: ReceiptLimits): Promise<void>;
  };
}
