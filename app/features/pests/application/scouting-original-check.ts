import { ScoutingRepository } from '../infrastructure/scouting-repository';

// Read only: no bootstrap, projection update, or correction replay.
export function readOriginalFieldCheck(db: D1Database, farmId: string, locationId: string, checkId: string) {
  return new ScoutingRepository(db).originalFieldCheck(farmId, locationId, checkId);
}
