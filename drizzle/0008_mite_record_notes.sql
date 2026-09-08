CREATE TABLE IF NOT EXISTS `mite_record_notes` (
	`id` text PRIMARY KEY NOT NULL,
	`farm_id` text NOT NULL,
	`capture_session_id` text NOT NULL,
	`track_key` text NOT NULL,
	`evidence_frame_prediction_id` text,
	`author_member_id` text,
	`author_name_snapshot` text NOT NULL,
	`author_role_snapshot` text NOT NULL,
	`language` text DEFAULT 'ko' NOT NULL,
	`content` text NOT NULL,
	`status` text DEFAULT 'ACTIVE' NOT NULL,
	`created_at` text NOT NULL,
	`updated_at` text NOT NULL,
	FOREIGN KEY (`farm_id`) REFERENCES `farms`(`id`) ON UPDATE no action ON DELETE cascade,
	FOREIGN KEY (`capture_session_id`) REFERENCES `capture_sessions`(`id`) ON UPDATE no action ON DELETE cascade,
	FOREIGN KEY (`evidence_frame_prediction_id`) REFERENCES `frame_predictions`(`id`) ON UPDATE no action ON DELETE set null,
	FOREIGN KEY (`author_member_id`) REFERENCES `farm_members`(`id`) ON UPDATE no action ON DELETE set null
);
--> statement-breakpoint
CREATE INDEX IF NOT EXISTS `idx_mite_record_notes_case_status_created`
ON `mite_record_notes` (`capture_session_id`,`track_key`,`status`,`created_at`);
--> statement-breakpoint
CREATE INDEX IF NOT EXISTS `idx_mite_record_notes_farm_status_created`
ON `mite_record_notes` (`farm_id`,`status`,`created_at`);
--> statement-breakpoint
CREATE TABLE IF NOT EXISTS `crop_stages` (
	`code` text PRIMARY KEY NOT NULL,
	`display_name_ko` text NOT NULL,
	`display_order` integer DEFAULT 0 NOT NULL
);
--> statement-breakpoint
CREATE TABLE IF NOT EXISTS `crop_guide_stages` (
	`id` text PRIMARY KEY NOT NULL,
	`guide_id` text NOT NULL,
	`stage_code` text NOT NULL,
	FOREIGN KEY (`guide_id`) REFERENCES `crop_guides`(`id`) ON UPDATE no action ON DELETE cascade,
	FOREIGN KEY (`stage_code`) REFERENCES `crop_stages`(`code`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE UNIQUE INDEX IF NOT EXISTS `uq_crop_guide_stages_guide_stage`
ON `crop_guide_stages` (`guide_id`,`stage_code`);
--> statement-breakpoint
CREATE INDEX IF NOT EXISTS `idx_crop_guide_stages_stage`
ON `crop_guide_stages` (`stage_code`,`guide_id`);
--> statement-breakpoint
CREATE TABLE IF NOT EXISTS `farm_member_events` (
	`id` text PRIMARY KEY NOT NULL,
	`farm_id` text NOT NULL,
	`target_member_id` text,
	`actor_member_id` text,
	`target_name_snapshot` text NOT NULL,
	`actor_name_snapshot` text NOT NULL,
	`event_type` text NOT NULL,
	`detail_json` text DEFAULT '{}' NOT NULL,
	`created_at` text NOT NULL,
	FOREIGN KEY (`farm_id`) REFERENCES `farms`(`id`) ON UPDATE no action ON DELETE cascade,
	FOREIGN KEY (`target_member_id`) REFERENCES `farm_members`(`id`) ON UPDATE no action ON DELETE set null,
	FOREIGN KEY (`actor_member_id`) REFERENCES `farm_members`(`id`) ON UPDATE no action ON DELETE set null
);
--> statement-breakpoint
CREATE INDEX IF NOT EXISTS `idx_farm_member_events_farm_created`
ON `farm_member_events` (`farm_id`,`created_at`);
--> statement-breakpoint
CREATE INDEX IF NOT EXISTS `idx_farm_member_events_target_created`
ON `farm_member_events` (`target_member_id`,`created_at`);
--> statement-breakpoint
CREATE TABLE IF NOT EXISTS `farm_notes` (
	`id` text PRIMARY KEY NOT NULL,
	`farm_id` text NOT NULL,
	`item_id` text,
	`author_member_id` text,
	`author_name_snapshot` text NOT NULL,
	`author_role_snapshot` text NOT NULL,
	`language` text DEFAULT 'ko' NOT NULL,
	`category` text NOT NULL,
	`title` text NOT NULL,
	`content` text NOT NULL,
	`pinned` integer DEFAULT 0 NOT NULL,
	`status` text DEFAULT 'ACTIVE' NOT NULL,
	`created_at` text NOT NULL,
	`updated_at` text NOT NULL,
	FOREIGN KEY (`farm_id`) REFERENCES `farms`(`id`) ON UPDATE no action ON DELETE cascade,
	FOREIGN KEY (`item_id`) REFERENCES `farm_items`(`id`) ON UPDATE no action ON DELETE set null,
	FOREIGN KEY (`author_member_id`) REFERENCES `farm_members`(`id`) ON UPDATE no action ON DELETE set null
);
--> statement-breakpoint
CREATE INDEX IF NOT EXISTS `idx_farm_notes_farm_status_updated`
ON `farm_notes` (`farm_id`,`status`,`updated_at`);
--> statement-breakpoint
CREATE INDEX IF NOT EXISTS `idx_farm_notes_item_updated`
ON `farm_notes` (`item_id`,`updated_at`);
--> statement-breakpoint
CREATE TABLE IF NOT EXISTS `prediction_review_events` (
	`id` text PRIMARY KEY NOT NULL,
	`farm_id` text NOT NULL,
	`frame_prediction_id` text NOT NULL,
	`reviewer_member_id` text,
	`reviewer_name_snapshot` text NOT NULL,
	`reviewer_role_snapshot` text NOT NULL,
	`verdict` text NOT NULL,
	`quick_note_code` text,
	`note` text DEFAULT '' NOT NULL,
	`note_language` text DEFAULT 'ko' NOT NULL,
	`created_at` text NOT NULL,
	FOREIGN KEY (`farm_id`) REFERENCES `farms`(`id`) ON UPDATE no action ON DELETE cascade,
	FOREIGN KEY (`frame_prediction_id`) REFERENCES `frame_predictions`(`id`) ON UPDATE no action ON DELETE cascade,
	FOREIGN KEY (`reviewer_member_id`) REFERENCES `farm_members`(`id`) ON UPDATE no action ON DELETE set null
);
--> statement-breakpoint
CREATE INDEX IF NOT EXISTS `idx_prediction_reviews_prediction_created`
ON `prediction_review_events` (`frame_prediction_id`,`created_at`);
--> statement-breakpoint
CREATE INDEX IF NOT EXISTS `idx_prediction_reviews_farm_created`
ON `prediction_review_events` (`farm_id`,`created_at`);
--> statement-breakpoint
CREATE TABLE IF NOT EXISTS `phone_verification_challenges` (
	`id` text PRIMARY KEY NOT NULL,
	`farm_id` text NOT NULL,
	`member_id` text,
	`phone` text NOT NULL,
	`code_hash` text NOT NULL,
	`expires_at` text NOT NULL,
	`attempts` integer DEFAULT 0 NOT NULL,
	`consumed_at` text,
	`created_at` text NOT NULL,
	FOREIGN KEY (`farm_id`) REFERENCES `farms`(`id`) ON UPDATE no action ON DELETE cascade,
	FOREIGN KEY (`member_id`) REFERENCES `farm_members`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE INDEX IF NOT EXISTS `idx_phone_challenges_member_created`
ON `phone_verification_challenges` (`member_id`,`created_at`);
--> statement-breakpoint
CREATE INDEX IF NOT EXISTS `idx_phone_challenges_expires`
ON `phone_verification_challenges` (`expires_at`);
--> statement-breakpoint
CREATE TABLE IF NOT EXISTS `notification_outbox` (
	`id` text PRIMARY KEY NOT NULL,
	`farm_id` text NOT NULL,
	`frame_prediction_id` text,
	`recipient_member_id` text,
	`recipient_phone` text NOT NULL,
	`notification_type` text NOT NULL,
	`payload_json` text DEFAULT '{}' NOT NULL,
	`status` text NOT NULL,
	`attempts` integer DEFAULT 0 NOT NULL,
	`last_error` text,
	`claimed_at` text,
	`created_at` text NOT NULL,
	`sent_at` text,
	FOREIGN KEY (`farm_id`) REFERENCES `farms`(`id`) ON UPDATE no action ON DELETE cascade,
	FOREIGN KEY (`frame_prediction_id`) REFERENCES `frame_predictions`(`id`) ON UPDATE no action ON DELETE cascade,
	FOREIGN KEY (`recipient_member_id`) REFERENCES `farm_members`(`id`) ON UPDATE no action ON DELETE set null
);
--> statement-breakpoint
CREATE INDEX IF NOT EXISTS `idx_notification_outbox_status_created`
ON `notification_outbox` (`status`,`created_at`);
--> statement-breakpoint
CREATE INDEX IF NOT EXISTS `idx_notification_outbox_farm_created`
ON `notification_outbox` (`farm_id`,`created_at`);
