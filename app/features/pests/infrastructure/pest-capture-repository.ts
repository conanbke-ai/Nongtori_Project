import type { PestCaptureRepositoryPort, PestCaptureSession } from '../application/pest-capture-service';

export class PestCaptureRepository implements PestCaptureRepositoryPort {
  constructor(private readonly db: D1Database) {}

  async hasActiveFarm(farmId: string) {
    return Boolean(await this.db.prepare("SELECT id FROM farms WHERE id = ? AND status = 'ACTIVE'").bind(farmId).first());
  }

  async hasActiveItem(farmId: string, itemId: string) {
    return Boolean(await this.db.prepare("SELECT id FROM farm_items WHERE id = ? AND farm_id = ? AND status = 'ACTIVE'")
      .bind(itemId, farmId).first());
  }

  async save({ sessionId, farmId, itemId, pestCode, createdAt, assets }: PestCaptureSession) {
    await this.db.batch([
      this.db.prepare(`INSERT INTO capture_sessions(
        id, farm_id, camera_id, item_id, house_id, bed_id, zone_id, capture_mode,
        source_type, processing_status, started_at, ended_at, created_at, pest_code
      ) VALUES (?, ?, NULL, ?, NULL, NULL, NULL, 'SINGLE_CAPTURE',
        'PERSONAL_CAPTURE', 'UPLOADED_AWAITING_MODEL', ?, NULL, ?, ?)`)
        .bind(sessionId, farmId, itemId, createdAt, createdAt, pestCode),
      ...assets.map(asset => this.db.prepare(`INSERT INTO capture_assets(
        id, capture_session_id, modality, object_key, original_name, content_type, size_bytes, created_at
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)`)
        .bind(asset.id, sessionId, asset.modality, asset.key, asset.file.name, asset.file.type, asset.file.size, createdAt)),
    ]);
  }
}
