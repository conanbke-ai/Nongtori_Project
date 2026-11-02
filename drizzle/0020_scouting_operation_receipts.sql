-- Prepared only: not wired into request-time bootstrap. No automatic expiry.
CREATE TABLE scouting_operation_receipts (
  farm_id TEXT NOT NULL,
  member_id TEXT NOT NULL,
  operation_kind TEXT NOT NULL CHECK(operation_kind IN ('CHECK','CORRECTION','ACTION','RESOLVE')),
  key_digest TEXT NOT NULL,
  canonical_version INTEGER NOT NULL CHECK(canonical_version = 1),
  payload_hash TEXT NOT NULL,
  http_status INTEGER NOT NULL CHECK(http_status IN (200,201)),
  response_json TEXT NOT NULL CHECK(length(CAST(response_json AS BLOB)) <= 4096),
  committed_at TEXT NOT NULL,
  PRIMARY KEY(farm_id, member_id, operation_kind, key_digest)
);
CREATE INDEX idx_scouting_receipts_farm_member ON scouting_operation_receipts(farm_id, member_id);
-- Transient guard row inserted/deleted inside the SAME batch; CHECK aborts it all.
CREATE TABLE scouting_operation_guards (
  id TEXT PRIMARY KEY NOT NULL,
  accepted INTEGER NOT NULL CONSTRAINT scouting_receipt_quota CHECK(accepted = 1)
);
