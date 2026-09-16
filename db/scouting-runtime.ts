import { env } from 'cloudflare:workers';

let scoutingReady: Promise<void> | undefined;

const statements = [
  `CREATE TABLE IF NOT EXISTS scouting_issue_catalog (
    code TEXT PRIMARY KEY NOT NULL, family TEXT NOT NULL, display_name_ko TEXT NOT NULL,
    ai_capability TEXT NOT NULL DEFAULT 'RECORD_ONLY', operational_status TEXT NOT NULL DEFAULT 'ACTIVE',
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
  )`,
  `CREATE TABLE IF NOT EXISTS scouting_location_states (
    id TEXT PRIMARY KEY NOT NULL, farm_id TEXT NOT NULL, house_id TEXT NOT NULL, bed_id TEXT NOT NULL, zone_id TEXT NOT NULL,
    location_key TEXT NOT NULL, house_code TEXT NOT NULL, bed_code TEXT NOT NULL, zone_code TEXT NOT NULL,
    current_state TEXT NOT NULL DEFAULT 'BASELINE', active_case_id TEXT, last_observed_at TEXT, last_field_check_at TEXT,
    last_action_at TEXT, last_alert_at TEXT, last_alert_reason TEXT, baseline_version TEXT,
    recent_pattern_fingerprint TEXT, state_version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(farm_id, location_key),
    FOREIGN KEY (farm_id) REFERENCES farms(id) ON DELETE CASCADE,
    FOREIGN KEY (house_id) REFERENCES houses(id) ON DELETE CASCADE,
    FOREIGN KEY (bed_id) REFERENCES beds(id) ON DELETE CASCADE,
    FOREIGN KEY (zone_id) REFERENCES zones(id) ON DELETE CASCADE
  )`,
  `CREATE INDEX IF NOT EXISTS idx_scouting_location_states_farm_state
    ON scouting_location_states(farm_id, current_state, updated_at)`,
  `CREATE TABLE IF NOT EXISTS scouting_cases (
    id TEXT PRIMARY KEY NOT NULL, farm_id TEXT NOT NULL, location_state_id TEXT NOT NULL,
    issue_family TEXT NOT NULL, primary_issue_code TEXT, status TEXT NOT NULL DEFAULT 'OPEN',
    opened_at TEXT NOT NULL, opened_reason TEXT NOT NULL, closed_at TEXT, close_reason TEXT,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    FOREIGN KEY (farm_id) REFERENCES farms(id) ON DELETE CASCADE,
    FOREIGN KEY (location_state_id) REFERENCES scouting_location_states(id) ON DELETE CASCADE,
    FOREIGN KEY (primary_issue_code) REFERENCES scouting_issue_catalog(code) ON DELETE SET NULL
  )`,
  `CREATE INDEX IF NOT EXISTS idx_scouting_cases_location_status
    ON scouting_cases(location_state_id, status, opened_at)`,
  `CREATE TABLE IF NOT EXISTS scouting_case_links (
    case_id TEXT PRIMARY KEY NOT NULL, previous_case_id TEXT, link_type TEXT NOT NULL DEFAULT 'RECURRENCE', created_at TEXT NOT NULL,
    FOREIGN KEY (case_id) REFERENCES scouting_cases(id) ON DELETE CASCADE,
    FOREIGN KEY (previous_case_id) REFERENCES scouting_cases(id) ON DELETE SET NULL
  )`,
  `CREATE INDEX IF NOT EXISTS idx_scouting_case_links_previous ON scouting_case_links(previous_case_id)`,
  `CREATE TABLE IF NOT EXISTS scouting_policy_profiles (
    policy_version TEXT PRIMARY KEY NOT NULL, freshness_mode TEXT NOT NULL,
    field_check_freshness_minutes INTEGER, status TEXT NOT NULL DEFAULT 'ACTIVE', created_at TEXT NOT NULL
  )`,
  `CREATE TABLE IF NOT EXISTS scouting_observations (
    id TEXT PRIMARY KEY NOT NULL, farm_id TEXT NOT NULL, location_state_id TEXT NOT NULL, case_id TEXT,
    capture_session_id TEXT, frame_id TEXT, source_asset_id TEXT, observed_at TEXT NOT NULL, source_type TEXT NOT NULL,
    leaf_temp REAL, ambient_temp REAL, reference_temp REAL, humidity REAL, light_level REAL,
    thermal_features_json TEXT NOT NULL DEFAULT '{}', rgb_reference_json TEXT NOT NULL DEFAULT '{}',
    model_name TEXT, model_version TEXT, risk_signal REAL, novelty_signal REAL, trend_signal REAL, spatial_signal REAL,
    pattern_fingerprint TEXT, policy_input_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL,
    FOREIGN KEY (farm_id) REFERENCES farms(id) ON DELETE CASCADE,
    FOREIGN KEY (location_state_id) REFERENCES scouting_location_states(id) ON DELETE CASCADE,
    FOREIGN KEY (case_id) REFERENCES scouting_cases(id) ON DELETE SET NULL,
    FOREIGN KEY (capture_session_id) REFERENCES capture_sessions(id) ON DELETE SET NULL,
    FOREIGN KEY (frame_id) REFERENCES frames(id) ON DELETE SET NULL
  )`,
  `CREATE INDEX IF NOT EXISTS idx_scouting_observations_location_time
    ON scouting_observations(location_state_id, observed_at)`,
  `CREATE TABLE IF NOT EXISTS scouting_field_checks (
    id TEXT PRIMARY KEY NOT NULL, farm_id TEXT NOT NULL, location_state_id TEXT NOT NULL, case_id TEXT, observation_id TEXT,
    checked_at TEXT NOT NULL, checker_member_id TEXT, primary_evidence_code TEXT NOT NULL,
    secondary_evidence_json TEXT NOT NULL DEFAULT '{}', note TEXT, photo_asset_id TEXT, created_at TEXT NOT NULL,
    FOREIGN KEY (farm_id) REFERENCES farms(id) ON DELETE CASCADE,
    FOREIGN KEY (location_state_id) REFERENCES scouting_location_states(id) ON DELETE CASCADE,
    FOREIGN KEY (case_id) REFERENCES scouting_cases(id) ON DELETE SET NULL,
    FOREIGN KEY (observation_id) REFERENCES scouting_observations(id) ON DELETE SET NULL,
    FOREIGN KEY (checker_member_id) REFERENCES farm_members(id) ON DELETE SET NULL
  )`,
  `CREATE TABLE IF NOT EXISTS scouting_field_check_corrections (
    id TEXT PRIMARY KEY NOT NULL, farm_id TEXT NOT NULL, field_check_id TEXT NOT NULL, location_state_id TEXT NOT NULL,
    case_id TEXT, correction_kind TEXT NOT NULL, replacement_evidence_code TEXT, reason_code TEXT NOT NULL,
    note TEXT, actor_member_id TEXT, created_at TEXT NOT NULL,
    FOREIGN KEY (farm_id) REFERENCES farms(id) ON DELETE CASCADE,
    FOREIGN KEY (field_check_id) REFERENCES scouting_field_checks(id) ON DELETE CASCADE,
    FOREIGN KEY (location_state_id) REFERENCES scouting_location_states(id) ON DELETE CASCADE,
    FOREIGN KEY (case_id) REFERENCES scouting_cases(id) ON DELETE SET NULL,
    FOREIGN KEY (actor_member_id) REFERENCES farm_members(id) ON DELETE SET NULL
  )`,
  `CREATE INDEX IF NOT EXISTS idx_scouting_field_check_corrections_check_time
    ON scouting_field_check_corrections(field_check_id, created_at)`,
  `CREATE TABLE IF NOT EXISTS scouting_actions (
    id TEXT PRIMARY KEY NOT NULL, farm_id TEXT NOT NULL, location_state_id TEXT NOT NULL, case_id TEXT,
    action_at TEXT NOT NULL, action_code TEXT NOT NULL, actor_member_id TEXT,
    detail_json TEXT NOT NULL DEFAULT '{}', note TEXT, created_at TEXT NOT NULL,
    FOREIGN KEY (farm_id) REFERENCES farms(id) ON DELETE CASCADE,
    FOREIGN KEY (location_state_id) REFERENCES scouting_location_states(id) ON DELETE CASCADE,
    FOREIGN KEY (case_id) REFERENCES scouting_cases(id) ON DELETE SET NULL,
    FOREIGN KEY (actor_member_id) REFERENCES farm_members(id) ON DELETE SET NULL
  )`,
  `CREATE TABLE IF NOT EXISTS scouting_case_events (
    id TEXT PRIMARY KEY NOT NULL, farm_id TEXT NOT NULL, location_state_id TEXT NOT NULL, case_id TEXT NOT NULL,
    event_type TEXT NOT NULL, reason_code TEXT, actor_member_id TEXT, detail_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL,
    FOREIGN KEY (farm_id) REFERENCES farms(id) ON DELETE CASCADE,
    FOREIGN KEY (location_state_id) REFERENCES scouting_location_states(id) ON DELETE CASCADE,
    FOREIGN KEY (case_id) REFERENCES scouting_cases(id) ON DELETE CASCADE,
    FOREIGN KEY (actor_member_id) REFERENCES farm_members(id) ON DELETE SET NULL
  )`,
  `CREATE INDEX IF NOT EXISTS idx_scouting_case_events_case_time ON scouting_case_events(case_id, created_at)`,
  `CREATE TABLE IF NOT EXISTS scouting_alert_events (
    id TEXT PRIMARY KEY NOT NULL, farm_id TEXT NOT NULL, location_state_id TEXT NOT NULL, case_id TEXT,
    observation_id TEXT NOT NULL, created_at TEXT NOT NULL, alert_decision TEXT NOT NULL, alert_reason TEXT NOT NULL,
    suppression_reason TEXT, policy_version TEXT NOT NULL, notification_outbox_id TEXT,
    FOREIGN KEY (farm_id) REFERENCES farms(id) ON DELETE CASCADE,
    FOREIGN KEY (location_state_id) REFERENCES scouting_location_states(id) ON DELETE CASCADE,
    FOREIGN KEY (case_id) REFERENCES scouting_cases(id) ON DELETE SET NULL,
    FOREIGN KEY (observation_id) REFERENCES scouting_observations(id) ON DELETE CASCADE,
    FOREIGN KEY (notification_outbox_id) REFERENCES notification_outbox(id) ON DELETE SET NULL
  )`,
  `INSERT OR IGNORE INTO scouting_issue_catalog(code, family, display_name_ko, ai_capability, operational_status, created_at, updated_at) VALUES
    ('SPIDER_MITE', 'PEST', '응애', 'ALERT_ONLY', 'ACTIVE', '2026-09-16T00:00:00.000Z', '2026-09-16T00:00:00.000Z'),
    ('APHID', 'PEST', '진딧물', 'RECORD_ONLY', 'ACTIVE', '2026-09-16T00:00:00.000Z', '2026-09-16T00:00:00.000Z'),
    ('THRIPS', 'PEST', '총채벌레', 'RECORD_ONLY', 'ACTIVE', '2026-09-16T00:00:00.000Z', '2026-09-16T00:00:00.000Z'),
    ('POWDERY_MILDEW', 'DISEASE', '흰가루병', 'RECORD_ONLY', 'ACTIVE', '2026-09-16T00:00:00.000Z', '2026-09-16T00:00:00.000Z'),
    ('GRAY_MOLD', 'DISEASE', '잿빛곰팡이병', 'RECORD_ONLY', 'ACTIVE', '2026-09-16T00:00:00.000Z', '2026-09-16T00:00:00.000Z'),
    ('UNKNOWN_PEST', 'PEST', '기타 해충·종류 미확인', 'RECORD_ONLY', 'ACTIVE', '2026-09-16T00:00:00.000Z', '2026-09-16T00:00:00.000Z'),
    ('UNKNOWN_DISEASE', 'DISEASE', '병해 의심·종류 미확인', 'RECORD_ONLY', 'ACTIVE', '2026-09-16T00:00:00.000Z', '2026-09-16T00:00:00.000Z'),
    ('ENVIRONMENTAL_STRESS', 'PHYSIOLOGICAL_ENVIRONMENTAL', '환경·생리 이상', 'ALERT_ONLY', 'ACTIVE', '2026-09-16T00:00:00.000Z', '2026-09-16T00:00:00.000Z'),
    ('UNKNOWN', 'UNKNOWN', '원인 미확인', 'RECORD_ONLY', 'ACTIVE', '2026-09-16T00:00:00.000Z', '2026-09-16T00:00:00.000Z')`,
  `INSERT OR IGNORE INTO scouting_policy_profiles(policy_version, freshness_mode, field_check_freshness_minutes, status, created_at)
    VALUES ('PEST-SCOUT-V2-20260916', 'CALIBRATION_PENDING', NULL, 'ACTIVE', '2026-09-16T00:00:00.000Z')`,
];

export function ensureScoutingRuntime() {
  if (!env.DB) throw new Error('Cloudflare D1 binding `DB` is unavailable.');
  const pending = scoutingReady ??= (async () => {
    await env.DB.batch(statements.map((sql) => env.DB.prepare(sql)));
    await env.DB.batch([
      env.DB.prepare('DROP TRIGGER IF EXISTS trg_mite_alert_notification_outbox_v3'),
      env.DB.prepare(`CREATE TRIGGER trg_mite_alert_notification_outbox_v3
        AFTER INSERT ON frame_predictions WHEN 0 BEGIN SELECT 1; END`),
    ]);
  })();
  return pending.catch((error) => {
    if (scoutingReady === pending) scoutingReady = undefined;
    throw error;
  });
}
