CREATE TABLE `frame_location_assignments` (
	`frame_id` text PRIMARY KEY NOT NULL,
	`farm_id` text NOT NULL,
	`house_id` text,
	`bed_id` text,
	`zone_id` text,
	`source` text DEFAULT 'MANUAL_CORRECTION' NOT NULL,
	`confidence` real,
	`created_at` text NOT NULL,
	`updated_at` text NOT NULL,
	FOREIGN KEY (`frame_id`) REFERENCES `frames`(`id`) ON UPDATE no action ON DELETE cascade,
	FOREIGN KEY (`farm_id`) REFERENCES `farms`(`id`) ON UPDATE no action ON DELETE cascade,
	FOREIGN KEY (`house_id`) REFERENCES `houses`(`id`) ON UPDATE no action ON DELETE set null,
	FOREIGN KEY (`bed_id`) REFERENCES `beds`(`id`) ON UPDATE no action ON DELETE set null,
	FOREIGN KEY (`zone_id`) REFERENCES `zones`(`id`) ON UPDATE no action ON DELETE set null,
	CONSTRAINT `ck_frame_location_assignments_source` CHECK(`source` in ('ROBOT_TELEMETRY', 'MANUAL_CORRECTION', 'MODEL_ESTIMATE')),
	CONSTRAINT `ck_frame_location_assignments_confidence` CHECK(`confidence` is null or (`confidence` >= 0 and `confidence` <= 1))
);
--> statement-breakpoint
CREATE INDEX `idx_frame_location_assignments_farm` ON `frame_location_assignments` (`farm_id`,`frame_id`);
--> statement-breakpoint
CREATE TRIGGER `trg_frame_location_assignment_scope_insert`
BEFORE INSERT ON `frame_location_assignments`
WHEN NOT EXISTS (
  SELECT 1 FROM frames frame JOIN capture_sessions session ON session.id = frame.capture_session_id
  WHERE frame.id = NEW.frame_id AND session.farm_id = NEW.farm_id
) OR (NEW.bed_id IS NOT NULL AND NEW.house_id IS NULL
) OR (NEW.zone_id IS NOT NULL AND (NEW.house_id IS NULL OR NEW.bed_id IS NULL)
) OR (NEW.house_id IS NOT NULL AND NOT EXISTS (
  SELECT 1 FROM houses house WHERE house.id = NEW.house_id AND house.farm_id = NEW.farm_id
)) OR (NEW.bed_id IS NOT NULL AND NOT EXISTS (
  SELECT 1 FROM beds bed JOIN houses house ON house.id = bed.house_id
  WHERE bed.id = NEW.bed_id AND house.farm_id = NEW.farm_id
    AND (NEW.house_id IS NULL OR bed.house_id = NEW.house_id)
)) OR (NEW.zone_id IS NOT NULL AND NOT EXISTS (
  SELECT 1 FROM zones zone JOIN beds bed ON bed.id = zone.bed_id
  JOIN houses house ON house.id = bed.house_id
  WHERE zone.id = NEW.zone_id AND house.farm_id = NEW.farm_id
    AND (NEW.house_id IS NULL OR house.id = NEW.house_id)
    AND (NEW.bed_id IS NULL OR bed.id = NEW.bed_id)
))
BEGIN SELECT RAISE(ABORT, 'FRAME_LOCATION_SCOPE_MISMATCH'); END;
--> statement-breakpoint
CREATE TRIGGER `trg_frame_location_assignment_scope_update`
BEFORE UPDATE OF frame_id, farm_id, house_id, bed_id, zone_id ON `frame_location_assignments`
WHEN NOT EXISTS (
  SELECT 1 FROM frames frame JOIN capture_sessions session ON session.id = frame.capture_session_id
  WHERE frame.id = NEW.frame_id AND session.farm_id = NEW.farm_id
) OR (NEW.bed_id IS NOT NULL AND NEW.house_id IS NULL
) OR (NEW.zone_id IS NOT NULL AND (NEW.house_id IS NULL OR NEW.bed_id IS NULL)
) OR (NEW.house_id IS NOT NULL AND NOT EXISTS (
  SELECT 1 FROM houses house WHERE house.id = NEW.house_id AND house.farm_id = NEW.farm_id
)) OR (NEW.bed_id IS NOT NULL AND NOT EXISTS (
  SELECT 1 FROM beds bed JOIN houses house ON house.id = bed.house_id
  WHERE bed.id = NEW.bed_id AND house.farm_id = NEW.farm_id
    AND (NEW.house_id IS NULL OR bed.house_id = NEW.house_id)
)) OR (NEW.zone_id IS NOT NULL AND NOT EXISTS (
  SELECT 1 FROM zones zone JOIN beds bed ON bed.id = zone.bed_id
  JOIN houses house ON house.id = bed.house_id
  WHERE zone.id = NEW.zone_id AND house.farm_id = NEW.farm_id
    AND (NEW.house_id IS NULL OR house.id = NEW.house_id)
    AND (NEW.bed_id IS NULL OR bed.id = NEW.bed_id)
))
BEGIN SELECT RAISE(ABORT, 'FRAME_LOCATION_SCOPE_MISMATCH'); END;
--> statement-breakpoint
CREATE TABLE `mite_record_note_translations` (
	`id` text PRIMARY KEY NOT NULL,
	`note_id` text NOT NULL,
	`source_language` text NOT NULL,
	`detected_source_language` text,
	`target_language` text NOT NULL,
	`source_updated_at` text NOT NULL,
	`translated_content` text NOT NULL,
	`provider` text DEFAULT 'GOOGLE_TRANSLATE_V2' NOT NULL,
	`model_version` text DEFAULT 'nmt' NOT NULL,
	`created_at` text NOT NULL,
	`updated_at` text NOT NULL,
	FOREIGN KEY (`note_id`) REFERENCES `mite_record_notes`(`id`) ON UPDATE no action ON DELETE cascade,
	CONSTRAINT `ck_mite_record_note_translations_target` CHECK(`target_language` in ('ko', 'vi', 'th', 'zh-CN'))
);
--> statement-breakpoint
CREATE UNIQUE INDEX `uq_mite_record_note_translations_target` ON `mite_record_note_translations` (`note_id`,`target_language`);
--> statement-breakpoint
CREATE INDEX `idx_mite_record_note_translations_note_source` ON `mite_record_note_translations` (`note_id`,`source_updated_at`);
