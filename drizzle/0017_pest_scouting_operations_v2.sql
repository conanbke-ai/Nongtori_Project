-- Pest scouting operations V2: append-only corrections, explicit case lifecycle, versioned freshness policy.

ALTER TABLE `scouting_cases` ADD COLUMN `previous_case_id` text REFERENCES `scouting_cases`(`id`) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS `idx_scouting_cases_previous_case`
  ON `scouting_cases` (`previous_case_id`);

CREATE TABLE IF NOT EXISTS `scouting_policy_profiles` (
  `policy_version` text PRIMARY KEY NOT NULL,
  `freshness_mode` text NOT NULL,
  `field_check_freshness_minutes` integer,
  `status` text NOT NULL DEFAULT 'ACTIVE',
  `created_at` text NOT NULL,
  CHECK (`freshness_mode` IN ('CALIBRATION_PENDING', 'FIXED_WINDOW')),
  CHECK (`status` IN ('ACTIVE', 'RETIRED')),
  CHECK (`field_check_freshness_minutes` IS NULL OR `field_check_freshness_minutes` > 0)
);

INSERT OR IGNORE INTO `scouting_policy_profiles`(
  `policy_version`, `freshness_mode`, `field_check_freshness_minutes`, `status`, `created_at`
) VALUES (
  'PEST-SCOUT-V2-20260916', 'CALIBRATION_PENDING', NULL, 'ACTIVE', '2026-09-16T00:00:00.000Z'
);

CREATE TABLE IF NOT EXISTS `scouting_field_check_corrections` (
  `id` text PRIMARY KEY NOT NULL,
  `farm_id` text NOT NULL,
  `field_check_id` text NOT NULL,
  `location_state_id` text NOT NULL,
  `case_id` text,
  `correction_kind` text NOT NULL,
  `replacement_evidence_code` text,
  `reason_code` text NOT NULL,
  `note` text,
  `actor_member_id` text,
  `created_at` text NOT NULL,
  FOREIGN KEY (`farm_id`) REFERENCES `farms`(`id`) ON DELETE CASCADE,
  FOREIGN KEY (`field_check_id`) REFERENCES `scouting_field_checks`(`id`) ON DELETE CASCADE,
  FOREIGN KEY (`location_state_id`) REFERENCES `scouting_location_states`(`id`) ON DELETE CASCADE,
  FOREIGN KEY (`case_id`) REFERENCES `scouting_cases`(`id`) ON DELETE SET NULL,
  FOREIGN KEY (`actor_member_id`) REFERENCES `farm_members`(`id`) ON DELETE SET NULL,
  CHECK (`correction_kind` IN ('REPLACE', 'VOID')),
  CHECK (`reason_code` IN ('MISCLICK', 'WRONG_OBSERVATION', 'DUPLICATE', 'OTHER')),
  CHECK (
    (`correction_kind` = 'REPLACE' AND `replacement_evidence_code` IS NOT NULL)
    OR (`correction_kind` = 'VOID' AND `replacement_evidence_code` IS NULL)
  )
);
CREATE INDEX IF NOT EXISTS `idx_scouting_field_check_corrections_check_time`
  ON `scouting_field_check_corrections` (`field_check_id`, `created_at`);
CREATE INDEX IF NOT EXISTS `idx_scouting_field_check_corrections_location_time`
  ON `scouting_field_check_corrections` (`location_state_id`, `created_at`);

CREATE TABLE IF NOT EXISTS `scouting_case_events` (
  `id` text PRIMARY KEY NOT NULL,
  `farm_id` text NOT NULL,
  `location_state_id` text NOT NULL,
  `case_id` text NOT NULL,
  `event_type` text NOT NULL,
  `reason_code` text,
  `actor_member_id` text,
  `detail_json` text NOT NULL DEFAULT '{}',
  `created_at` text NOT NULL,
  FOREIGN KEY (`farm_id`) REFERENCES `farms`(`id`) ON DELETE CASCADE,
  FOREIGN KEY (`location_state_id`) REFERENCES `scouting_location_states`(`id`) ON DELETE CASCADE,
  FOREIGN KEY (`case_id`) REFERENCES `scouting_cases`(`id`) ON DELETE CASCADE,
  FOREIGN KEY (`actor_member_id`) REFERENCES `farm_members`(`id`) ON DELETE SET NULL,
  CHECK (`event_type` IN ('OPENED', 'RESOLVED', 'RECURRENCE_OPENED', 'FIELD_CHECK_CORRECTED'))
);
CREATE INDEX IF NOT EXISTS `idx_scouting_case_events_case_time`
  ON `scouting_case_events` (`case_id`, `created_at`);
CREATE INDEX IF NOT EXISTS `idx_scouting_case_events_location_time`
  ON `scouting_case_events` (`location_state_id`, `created_at`);
