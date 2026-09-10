ALTER TABLE `mite_record_notes` ADD `target_frame_id` text REFERENCES `frames`(`id`) ON DELETE set null;
--> statement-breakpoint
ALTER TABLE `mite_record_notes` ADD `parent_note_id` text REFERENCES `mite_record_notes`(`id`) ON DELETE set null;
--> statement-breakpoint
ALTER TABLE `mite_record_notes` ADD `author_account_snapshot` text DEFAULT '' NOT NULL;
--> statement-breakpoint
UPDATE `mite_record_notes`
SET `target_frame_id` = (
  SELECT `frame_predictions`.`frame_id`
  FROM `frame_predictions`
  WHERE `frame_predictions`.`id` = `mite_record_notes`.`evidence_frame_prediction_id`
)
WHERE `target_frame_id` IS NULL AND `evidence_frame_prediction_id` IS NOT NULL;
--> statement-breakpoint
UPDATE `mite_record_notes`
SET `author_account_snapshot` =
  substr(`author_role_snapshot`, 1, 1) || '-' ||
  CASE
    WHEN `author_member_id` IS NULL THEN 'OLD'
    ELSE upper(substr(replace(`author_member_id`, '-', ''), -4))
  END
WHERE `author_account_snapshot` = '';
--> statement-breakpoint
CREATE INDEX IF NOT EXISTS `idx_mite_record_notes_frame_status_created`
ON `mite_record_notes` (`capture_session_id`,`target_frame_id`,`status`,`created_at`);
--> statement-breakpoint
CREATE INDEX IF NOT EXISTS `idx_mite_record_notes_parent_status_created`
ON `mite_record_notes` (`parent_note_id`,`status`,`created_at`);
--> statement-breakpoint
CREATE TRIGGER IF NOT EXISTS `trg_mite_record_note_parent_scope`
BEFORE INSERT ON `mite_record_notes`
WHEN NEW.`parent_note_id` IS NOT NULL AND NOT EXISTS (
  SELECT 1 FROM `mite_record_notes` parent
  WHERE parent.`id` = NEW.`parent_note_id`
    AND parent.`farm_id` = NEW.`farm_id`
    AND parent.`capture_session_id` = NEW.`capture_session_id`
    AND parent.`status` = 'ACTIVE'
    AND (
      parent.`target_frame_id` = NEW.`target_frame_id`
      OR (
        parent.`target_frame_id` IS NULL
        AND NEW.`target_frame_id` IS NULL
        AND parent.`track_key` = NEW.`track_key`
      )
    )
)
BEGIN
  SELECT RAISE(ABORT, 'NOTE_PARENT_SCOPE_MISMATCH');
END;
--> statement-breakpoint
CREATE TRIGGER IF NOT EXISTS `trg_mite_record_note_frame_session`
BEFORE INSERT ON `mite_record_notes`
WHEN NEW.`target_frame_id` IS NOT NULL AND NOT EXISTS (
  SELECT 1 FROM `frames` frame
  WHERE frame.`id` = NEW.`target_frame_id`
    AND frame.`capture_session_id` = NEW.`capture_session_id`
)
BEGIN
  SELECT RAISE(ABORT, 'NOTE_FRAME_SESSION_MISMATCH');
END;
