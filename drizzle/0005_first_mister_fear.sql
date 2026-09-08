CREATE TABLE `capture_assets` (
	`id` text PRIMARY KEY NOT NULL,
	`capture_session_id` text NOT NULL,
	`modality` text NOT NULL,
	`object_key` text NOT NULL,
	`original_name` text NOT NULL,
	`content_type` text NOT NULL,
	`size_bytes` integer NOT NULL,
	`created_at` text NOT NULL,
	FOREIGN KEY (`capture_session_id`) REFERENCES `capture_sessions`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE UNIQUE INDEX `capture_assets_object_key_unique` ON `capture_assets` (`object_key`);--> statement-breakpoint
CREATE INDEX `idx_capture_assets_session` ON `capture_assets` (`capture_session_id`,`modality`);--> statement-breakpoint
CREATE TABLE `crop_types` (
	`code` text PRIMARY KEY NOT NULL,
	`display_name_ko` text NOT NULL,
	`created_at` text NOT NULL
);
--> statement-breakpoint
CREATE TABLE `farm_items` (
	`id` text PRIMARY KEY NOT NULL,
	`farm_id` text NOT NULL,
	`crop_code` text NOT NULL,
	`cultivar_code` text,
	`display_name` text NOT NULL,
	`status` text DEFAULT 'ACTIVE' NOT NULL,
	`created_at` text NOT NULL,
	`updated_at` text NOT NULL,
	FOREIGN KEY (`farm_id`) REFERENCES `farms`(`id`) ON UPDATE no action ON DELETE cascade,
	FOREIGN KEY (`crop_code`) REFERENCES `crop_types`(`code`) ON UPDATE no action ON DELETE no action,
	FOREIGN KEY (`cultivar_code`) REFERENCES `cultivars`(`code`) ON UPDATE no action ON DELETE no action
);
--> statement-breakpoint
CREATE UNIQUE INDEX `uq_farm_items_crop_cultivar` ON `farm_items` (`farm_id`,`crop_code`,`cultivar_code`);--> statement-breakpoint
CREATE INDEX `idx_farm_items_farm_status` ON `farm_items` (`farm_id`,`status`);--> statement-breakpoint
CREATE TABLE `farm_members` (
	`id` text PRIMARY KEY NOT NULL,
	`farm_id` text NOT NULL,
	`login_id` text NOT NULL,
	`identity_provider` text NOT NULL,
	`identity_subject` text,
	`email` text,
	`display_name` text,
	`phone` text,
	`phone_verified_at` text,
	`notifications_enabled` integer DEFAULT 0 NOT NULL,
	`preferred_language` text DEFAULT 'ko' NOT NULL,
	`invited_by_member_id` text,
	`approved_at` text,
	`role` text DEFAULT 'WORKER' NOT NULL,
	`status` text DEFAULT 'ACTIVE' NOT NULL,
	`created_at` text NOT NULL,
	`updated_at` text NOT NULL,
	FOREIGN KEY (`farm_id`) REFERENCES `farms`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE UNIQUE INDEX `uq_farm_members_login` ON `farm_members` (`login_id`);--> statement-breakpoint
CREATE UNIQUE INDEX `uq_farm_members_provider_subject` ON `farm_members` (`identity_provider`,`identity_subject`);--> statement-breakpoint
CREATE INDEX `idx_farm_members_farm_status` ON `farm_members` (`farm_id`,`status`);--> statement-breakpoint
ALTER TABLE `cameras` ADD `stream_url` text;--> statement-breakpoint
ALTER TABLE `cameras` ADD `connection_status` text DEFAULT 'DISCONNECTED' NOT NULL;--> statement-breakpoint
ALTER TABLE `cameras` ADD `last_seen_at` text;--> statement-breakpoint
ALTER TABLE `capture_sessions` ADD `item_id` text REFERENCES farm_items(id) ON DELETE SET NULL;--> statement-breakpoint
ALTER TABLE `fruit_assessments` ADD `farm_id` text REFERENCES farms(id);--> statement-breakpoint
ALTER TABLE `fruit_assessments` ADD `capture_session_id` text REFERENCES capture_sessions(id);--> statement-breakpoint
ALTER TABLE `fruit_assessments` ADD `source_type` text DEFAULT 'PERSONAL_CAPTURE' NOT NULL;--> statement-breakpoint
ALTER TABLE `fruit_assessments` ADD `capture_at` text;--> statement-breakpoint
CREATE INDEX `idx_fruit_assessments_farm_capture` ON `fruit_assessments` (`farm_id`,`capture_at`);
