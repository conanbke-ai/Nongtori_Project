-- Append-only runtime weight provenance for fruit assessments.
-- Field Weight_g remains training ground truth and is not migrated into this table.

CREATE TABLE IF NOT EXISTS `fruit_weight_observations` (
  `id` text PRIMARY KEY NOT NULL,
  `fruit_assessment_id` text NOT NULL,
  `source` text NOT NULL,
  `weight_g` real NOT NULL,
  `confidence` real,
  `model_name` text,
  `model_version` text,
  `source_ref` text,
  `measured_at` text,
  `created_by_member_id` text,
  `created_at` text NOT NULL,
  FOREIGN KEY (`fruit_assessment_id`) REFERENCES `fruit_assessments`(`id`) ON DELETE CASCADE,
  FOREIGN KEY (`created_by_member_id`) REFERENCES `farm_members`(`id`) ON DELETE SET NULL,
  CHECK (`source` IN ('SENSOR_MEASURED', 'MANUAL_MEASURED', 'VISION_ESTIMATED')),
  CHECK (`weight_g` > 0),
  CHECK (`confidence` IS NULL OR (`confidence` >= 0 AND `confidence` <= 1)),
  CHECK (
    (`source` = 'VISION_ESTIMATED' AND `model_name` IS NOT NULL AND `model_version` IS NOT NULL)
    OR
    (`source` != 'VISION_ESTIMATED' AND `model_name` IS NULL AND `model_version` IS NULL AND `confidence` IS NULL)
  )
);

CREATE INDEX IF NOT EXISTS `idx_fruit_weight_observations_assessment_created`
  ON `fruit_weight_observations` (`fruit_assessment_id`, `created_at`);

CREATE INDEX IF NOT EXISTS `idx_fruit_weight_observations_assessment_source`
  ON `fruit_weight_observations` (`fruit_assessment_id`, `source`, `created_at`);
