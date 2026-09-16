-- Stateful pest scouting runtime. All observations are append-only; alert decisions are recorded separately.

-- Disable the legacy stateless mite notification trigger without letting ensureSchema recreate it.
DROP TRIGGER IF EXISTS `trg_mite_alert_notification_outbox_v3`;
CREATE TRIGGER `trg_mite_alert_notification_outbox_v3`
AFTER INSERT ON `frame_predictions`
WHEN 0
BEGIN
  SELECT 1;
END;

CREATE TABLE IF NOT EXISTS `scouting_issue_catalog` (
  `code` text PRIMARY KEY NOT NULL,
  `family` text NOT NULL,
  `display_name_ko` text NOT NULL,
  `ai_capability` text NOT NULL DEFAULT 'RECORD_ONLY',
  `operational_status` text NOT NULL DEFAULT 'ACTIVE',
  `created_at` text NOT NULL,
  `updated_at` text NOT NULL,
  CHECK (`family` IN ('PEST', 'DISEASE', 'PHYSIOLOGICAL_ENVIRONMENTAL', 'UNKNOWN')),
  CHECK (`ai_capability` IN ('SUPPORTED', 'ALERT_ONLY', 'RECORD_ONLY'))
);

INSERT OR IGNORE INTO `scouting_issue_catalog`
  (`code`, `family`, `display_name_ko`, `ai_capability`, `operational_status`, `created_at`, `updated_at`)
VALUES
  ('SPIDER_MITE', 'PEST', '응애', 'ALERT_ONLY', 'ACTIVE', '2026-09-16T00:00:00.000Z', '2026-09-16T00:00:00.000Z'),
  ('APHID', 'PEST', '진딧물', 'RECORD_ONLY', 'ACTIVE', '2026-09-16T00:00:00.000Z', '2026-09-16T00:00:00.000Z'),
  ('THRIPS', 'PEST', '총채벌레', 'RECORD_ONLY', 'ACTIVE', '2026-09-16T00:00:00.000Z', '2026-09-16T00:00:00.000Z'),
  ('POWDERY_MILDEW', 'DISEASE', '흰가루병', 'RECORD_ONLY', 'ACTIVE', '2026-09-16T00:00:00.000Z', '2026-09-16T00:00:00.000Z'),
  ('GRAY_MOLD', 'DISEASE', '잿빛곰팡이병', 'RECORD_ONLY', 'ACTIVE', '2026-09-16T00:00:00.000Z', '2026-09-16T00:00:00.000Z'),
  ('UNKNOWN_PEST', 'PEST', '기타 해충·종류 미확인', 'RECORD_ONLY', 'ACTIVE', '2026-09-16T00:00:00.000Z', '2026-09-16T00:00:00.000Z'),
  ('UNKNOWN_DISEASE', 'DISEASE', '병해 의심·종류 미확인', 'RECORD_ONLY', 'ACTIVE', '2026-09-16T00:00:00.000Z', '2026-09-16T00:00:00.000Z'),
  ('ENVIRONMENTAL_STRESS', 'PHYSIOLOGICAL_ENVIRONMENTAL', '환경·생리 이상', 'ALERT_ONLY', 'ACTIVE', '2026-09-16T00:00:00.000Z', '2026-09-16T00:00:00.000Z'),
  ('UNKNOWN', 'UNKNOWN', '원인 미확인', 'RECORD_ONLY', 'ACTIVE', '2026-09-16T00:00:00.000Z', '2026-09-16T00:00:00.000Z');

CREATE TABLE IF NOT EXISTS `scouting_location_states` (
  `id` text PRIMARY KEY NOT NULL,
  `farm_id` text NOT NULL,
  `house_id` text NOT NULL,
  `bed_id` text NOT NULL,
  `zone_id` text NOT NULL,
  `location_key` text NOT NULL,
  `house_code` text NOT NULL,
  `bed_code` text NOT NULL,
  `zone_code` text NOT NULL,
  `current_state` text NOT NULL DEFAULT 'BASELINE',
  `active_case_id` text,
  `last_observed_at` text,
  `last_field_check_at` text,
  `last_action_at` text,
  `last_alert_at` text,
  `last_alert_reason` text,
  `baseline_version` text,
  `recent_pattern_fingerprint` text,
  `state_version` integer NOT NULL DEFAULT 1,
  `created_at` text NOT NULL,
  `updated_at` text NOT NULL,
  FOREIGN KEY (`farm_id`) REFERENCES `farms`(`id`) ON DELETE CASCADE,
  FOREIGN KEY (`house_id`) REFERENCES `houses`(`id`) ON DELETE CASCADE,
  FOREIGN KEY (`bed_id`) REFERENCES `beds`(`id`) ON DELETE CASCADE,
  FOREIGN KEY (`zone_id`) REFERENCES `zones`(`id`) ON DELETE CASCADE,
  UNIQUE (`farm_id`, `location_key`),
  CHECK (`current_state` IN ('BASELINE', 'WATCH', 'FIELD_CHECK_REQUIRED', 'SUSPECTED', 'CONFIRMED', 'POST_TREATMENT', 'MONITORING', 'RESOLVED'))
);
CREATE INDEX IF NOT EXISTS `idx_scouting_location_states_farm_state`
  ON `scouting_location_states` (`farm_id`, `current_state`, `updated_at`);
CREATE INDEX IF NOT EXISTS `idx_scouting_location_states_zone`
  ON `scouting_location_states` (`zone_id`, `updated_at`);

CREATE TABLE IF NOT EXISTS `scouting_cases` (
  `id` text PRIMARY KEY NOT NULL,
  `farm_id` text NOT NULL,
  `location_state_id` text NOT NULL,
  `issue_family` text NOT NULL,
  `primary_issue_code` text,
  `status` text NOT NULL DEFAULT 'OPEN',
  `opened_at` text NOT NULL,
  `opened_reason` text NOT NULL,
  `closed_at` text,
  `close_reason` text,
  `created_at` text NOT NULL,
  `updated_at` text NOT NULL,
  FOREIGN KEY (`farm_id`) REFERENCES `farms`(`id`) ON DELETE CASCADE,
  FOREIGN KEY (`location_state_id`) REFERENCES `scouting_location_states`(`id`) ON DELETE CASCADE,
  FOREIGN KEY (`primary_issue_code`) REFERENCES `scouting_issue_catalog`(`code`) ON DELETE SET NULL,
  CHECK (`issue_family` IN ('PEST', 'DISEASE', 'PHYSIOLOGICAL_ENVIRONMENTAL', 'UNKNOWN')),
  CHECK (`status` IN ('OPEN', 'MONITORING', 'POST_TREATMENT', 'RESOLVED'))
);
CREATE INDEX IF NOT EXISTS `idx_scouting_cases_location_status`
  ON `scouting_cases` (`location_state_id`, `status`, `opened_at`);
CREATE INDEX IF NOT EXISTS `idx_scouting_cases_farm_status`
  ON `scouting_cases` (`farm_id`, `status`, `updated_at`);

CREATE TABLE IF NOT EXISTS `scouting_observations` (
  `id` text PRIMARY KEY NOT NULL,
  `farm_id` text NOT NULL,
  `location_state_id` text NOT NULL,
  `case_id` text,
  `capture_session_id` text,
  `frame_id` text,
  `source_asset_id` text,
  `observed_at` text NOT NULL,
  `source_type` text NOT NULL,
  `leaf_temp` real,
  `ambient_temp` real,
  `reference_temp` real,
  `humidity` real,
  `light_level` real,
  `thermal_features_json` text NOT NULL DEFAULT '{}',
  `rgb_reference_json` text NOT NULL DEFAULT '{}',
  `model_name` text,
  `model_version` text,
  `risk_signal` real,
  `novelty_signal` real,
  `trend_signal` real,
  `spatial_signal` real,
  `pattern_fingerprint` text,
  `policy_input_json` text NOT NULL DEFAULT '{}',
  `created_at` text NOT NULL,
  FOREIGN KEY (`farm_id`) REFERENCES `farms`(`id`) ON DELETE CASCADE,
  FOREIGN KEY (`location_state_id`) REFERENCES `scouting_location_states`(`id`) ON DELETE CASCADE,
  FOREIGN KEY (`case_id`) REFERENCES `scouting_cases`(`id`) ON DELETE SET NULL,
  FOREIGN KEY (`capture_session_id`) REFERENCES `capture_sessions`(`id`) ON DELETE SET NULL,
  FOREIGN KEY (`frame_id`) REFERENCES `frames`(`id`) ON DELETE SET NULL,
  CHECK (`source_type` IN ('THERMAL', 'RGB_REFERENCE', 'SENSOR', 'MANUAL', 'FUSION'))
);
CREATE INDEX IF NOT EXISTS `idx_scouting_observations_location_time`
  ON `scouting_observations` (`location_state_id`, `observed_at`);
CREATE INDEX IF NOT EXISTS `idx_scouting_observations_case_time`
  ON `scouting_observations` (`case_id`, `observed_at`);
CREATE INDEX IF NOT EXISTS `idx_scouting_observations_session`
  ON `scouting_observations` (`capture_session_id`, `observed_at`);

CREATE TABLE IF NOT EXISTS `scouting_field_checks` (
  `id` text PRIMARY KEY NOT NULL,
  `farm_id` text NOT NULL,
  `location_state_id` text NOT NULL,
  `case_id` text,
  `observation_id` text,
  `checked_at` text NOT NULL,
  `checker_member_id` text,
  `primary_evidence_code` text NOT NULL,
  `secondary_evidence_json` text NOT NULL DEFAULT '{}',
  `note` text,
  `photo_asset_id` text,
  `created_at` text NOT NULL,
  FOREIGN KEY (`farm_id`) REFERENCES `farms`(`id`) ON DELETE CASCADE,
  FOREIGN KEY (`location_state_id`) REFERENCES `scouting_location_states`(`id`) ON DELETE CASCADE,
  FOREIGN KEY (`case_id`) REFERENCES `scouting_cases`(`id`) ON DELETE SET NULL,
  FOREIGN KEY (`observation_id`) REFERENCES `scouting_observations`(`id`) ON DELETE SET NULL,
  FOREIGN KEY (`checker_member_id`) REFERENCES `farm_members`(`id`) ON DELETE SET NULL,
  CHECK (`primary_evidence_code` IN (
    'NO_VISIBLE_EVIDENCE', 'LEAF_DAMAGE_OBSERVED', 'WEBBING_OR_MITE_TRACE_SUSPECTED',
    'DIRECT_MITE_OR_EGG_CONFIRMED', 'OTHER_PEST_LIKE_EVIDENCE', 'DISEASE_LIKE_EVIDENCE',
    'PHYSIOLOGICAL_OR_ENVIRONMENTAL_ABNORMALITY', 'INCONCLUSIVE'
  ))
);
CREATE INDEX IF NOT EXISTS `idx_scouting_field_checks_location_time`
  ON `scouting_field_checks` (`location_state_id`, `checked_at`);
CREATE INDEX IF NOT EXISTS `idx_scouting_field_checks_case_time`
  ON `scouting_field_checks` (`case_id`, `checked_at`);

CREATE TABLE IF NOT EXISTS `scouting_actions` (
  `id` text PRIMARY KEY NOT NULL,
  `farm_id` text NOT NULL,
  `location_state_id` text NOT NULL,
  `case_id` text,
  `action_at` text NOT NULL,
  `action_code` text NOT NULL,
  `actor_member_id` text,
  `detail_json` text NOT NULL DEFAULT '{}',
  `note` text,
  `created_at` text NOT NULL,
  FOREIGN KEY (`farm_id`) REFERENCES `farms`(`id`) ON DELETE CASCADE,
  FOREIGN KEY (`location_state_id`) REFERENCES `scouting_location_states`(`id`) ON DELETE CASCADE,
  FOREIGN KEY (`case_id`) REFERENCES `scouting_cases`(`id`) ON DELETE SET NULL,
  FOREIGN KEY (`actor_member_id`) REFERENCES `farm_members`(`id`) ON DELETE SET NULL,
  CHECK (`action_code` IN ('TREATMENT_APPLIED', 'LEAF_REMOVED', 'BIOCONTROL_APPLIED', 'OBSERVE_ONLY', 'OTHER_ACTION'))
);
CREATE INDEX IF NOT EXISTS `idx_scouting_actions_location_time`
  ON `scouting_actions` (`location_state_id`, `action_at`);
CREATE INDEX IF NOT EXISTS `idx_scouting_actions_case_time`
  ON `scouting_actions` (`case_id`, `action_at`);

CREATE TABLE IF NOT EXISTS `scouting_alert_events` (
  `id` text PRIMARY KEY NOT NULL,
  `farm_id` text NOT NULL,
  `location_state_id` text NOT NULL,
  `case_id` text,
  `observation_id` text NOT NULL,
  `created_at` text NOT NULL,
  `alert_decision` text NOT NULL,
  `alert_reason` text NOT NULL,
  `suppression_reason` text,
  `policy_version` text NOT NULL,
  `notification_outbox_id` text,
  FOREIGN KEY (`farm_id`) REFERENCES `farms`(`id`) ON DELETE CASCADE,
  FOREIGN KEY (`location_state_id`) REFERENCES `scouting_location_states`(`id`) ON DELETE CASCADE,
  FOREIGN KEY (`case_id`) REFERENCES `scouting_cases`(`id`) ON DELETE SET NULL,
  FOREIGN KEY (`observation_id`) REFERENCES `scouting_observations`(`id`) ON DELETE CASCADE,
  FOREIGN KEY (`notification_outbox_id`) REFERENCES `notification_outbox`(`id`) ON DELETE SET NULL,
  CHECK (`alert_decision` IN ('ISSUED', 'SUPPRESSED', 'ESCALATED', 'RECHECK_REQUESTED'))
);
CREATE INDEX IF NOT EXISTS `idx_scouting_alert_events_location_time`
  ON `scouting_alert_events` (`location_state_id`, `created_at`);
CREATE INDEX IF NOT EXISTS `idx_scouting_alert_events_decision_time`
  ON `scouting_alert_events` (`alert_decision`, `created_at`);
