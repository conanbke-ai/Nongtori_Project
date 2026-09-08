CREATE TABLE `beds` (
	`id` text PRIMARY KEY NOT NULL,
	`house_id` text NOT NULL,
	`code` text NOT NULL,
	`name` text NOT NULL,
	`display_order` integer DEFAULT 0 NOT NULL,
	`status` text DEFAULT 'ACTIVE' NOT NULL,
	`metadata_json` text DEFAULT '{}' NOT NULL,
	`created_at` text NOT NULL,
	`updated_at` text NOT NULL,
	FOREIGN KEY (`house_id`) REFERENCES `houses`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE UNIQUE INDEX `uq_beds_house_code` ON `beds` (`house_id`,`code`);--> statement-breakpoint
CREATE INDEX `idx_beds_house_order` ON `beds` (`house_id`,`display_order`);--> statement-breakpoint
CREATE TABLE `cameras` (
	`id` text PRIMARY KEY NOT NULL,
	`farm_id` text NOT NULL,
	`house_id` text,
	`bed_id` text,
	`zone_id` text,
	`code` text NOT NULL,
	`name` text NOT NULL,
	`camera_type` text NOT NULL,
	`source_type` text NOT NULL,
	`external_ref` text,
	`status` text DEFAULT 'ACTIVE' NOT NULL,
	`created_at` text NOT NULL,
	`updated_at` text NOT NULL,
	FOREIGN KEY (`farm_id`) REFERENCES `farms`(`id`) ON UPDATE no action ON DELETE cascade,
	FOREIGN KEY (`house_id`) REFERENCES `houses`(`id`) ON UPDATE no action ON DELETE set null,
	FOREIGN KEY (`bed_id`) REFERENCES `beds`(`id`) ON UPDATE no action ON DELETE set null,
	FOREIGN KEY (`zone_id`) REFERENCES `zones`(`id`) ON UPDATE no action ON DELETE set null
);
--> statement-breakpoint
CREATE UNIQUE INDEX `uq_cameras_farm_code` ON `cameras` (`farm_id`,`code`);--> statement-breakpoint
CREATE INDEX `idx_cameras_zone` ON `cameras` (`zone_id`,`status`);--> statement-breakpoint
CREATE TABLE `capture_sessions` (
	`id` text PRIMARY KEY NOT NULL,
	`farm_id` text NOT NULL,
	`camera_id` text,
	`house_id` text,
	`bed_id` text,
	`zone_id` text,
	`capture_mode` text NOT NULL,
	`source_type` text NOT NULL,
	`processing_status` text NOT NULL,
	`started_at` text NOT NULL,
	`ended_at` text,
	`created_at` text NOT NULL,
	FOREIGN KEY (`farm_id`) REFERENCES `farms`(`id`) ON UPDATE no action ON DELETE cascade,
	FOREIGN KEY (`camera_id`) REFERENCES `cameras`(`id`) ON UPDATE no action ON DELETE set null,
	FOREIGN KEY (`house_id`) REFERENCES `houses`(`id`) ON UPDATE no action ON DELETE set null,
	FOREIGN KEY (`bed_id`) REFERENCES `beds`(`id`) ON UPDATE no action ON DELETE set null,
	FOREIGN KEY (`zone_id`) REFERENCES `zones`(`id`) ON UPDATE no action ON DELETE set null
);
--> statement-breakpoint
CREATE INDEX `idx_capture_sessions_farm_started` ON `capture_sessions` (`farm_id`,`started_at`);--> statement-breakpoint
CREATE INDEX `idx_capture_sessions_processing` ON `capture_sessions` (`processing_status`,`created_at`);--> statement-breakpoint
CREATE TABLE `config_import_runs` (
	`id` text PRIMARY KEY NOT NULL,
	`source_id` text NOT NULL,
	`status` text NOT NULL,
	`rows_read` integer DEFAULT 0 NOT NULL,
	`rows_created` integer DEFAULT 0 NOT NULL,
	`rows_updated` integer DEFAULT 0 NOT NULL,
	`rows_rejected` integer DEFAULT 0 NOT NULL,
	`checksum` text,
	`error_summary` text,
	`started_at` text NOT NULL,
	`finished_at` text,
	FOREIGN KEY (`source_id`) REFERENCES `config_sources`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE INDEX `idx_config_import_runs_source` ON `config_import_runs` (`source_id`,`started_at`);--> statement-breakpoint
CREATE TABLE `config_sources` (
	`id` text PRIMARY KEY NOT NULL,
	`farm_id` text,
	`source_type` text NOT NULL,
	`spreadsheet_id` text,
	`sheet_gid` text,
	`access_mode` text DEFAULT 'READ_ONLY' NOT NULL,
	`mapping_json` text DEFAULT '{}' NOT NULL,
	`status` text NOT NULL,
	`last_imported_at` text,
	`created_at` text NOT NULL,
	`updated_at` text NOT NULL,
	FOREIGN KEY (`farm_id`) REFERENCES `farms`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE INDEX `idx_config_sources_farm` ON `config_sources` (`farm_id`,`status`);--> statement-breakpoint
CREATE TABLE `farm_cultivars` (
	`id` text PRIMARY KEY NOT NULL,
	`farm_id` text NOT NULL,
	`cultivar_code` text NOT NULL,
	`status` text DEFAULT 'ACTIVE' NOT NULL,
	`created_at` text NOT NULL,
	FOREIGN KEY (`farm_id`) REFERENCES `farms`(`id`) ON UPDATE no action ON DELETE cascade,
	FOREIGN KEY (`cultivar_code`) REFERENCES `cultivars`(`code`) ON UPDATE no action ON DELETE no action
);
--> statement-breakpoint
CREATE UNIQUE INDEX `uq_farm_cultivars` ON `farm_cultivars` (`farm_id`,`cultivar_code`);--> statement-breakpoint
CREATE TABLE `farms` (
	`id` text PRIMARY KEY NOT NULL,
	`code` text NOT NULL,
	`name` text NOT NULL,
	`timezone` text DEFAULT 'Asia/Seoul' NOT NULL,
	`status` text DEFAULT 'ACTIVE' NOT NULL,
	`created_at` text NOT NULL,
	`updated_at` text NOT NULL
);
--> statement-breakpoint
CREATE UNIQUE INDEX `farms_code_unique` ON `farms` (`code`);--> statement-breakpoint
CREATE INDEX `idx_farms_status` ON `farms` (`status`,`name`);--> statement-breakpoint
CREATE TABLE `frame_predictions` (
	`id` text PRIMARY KEY NOT NULL,
	`inference_run_id` text NOT NULL,
	`frame_id` text NOT NULL,
	`track_id` text,
	`class_label` text NOT NULL,
	`confidence` real,
	`decision_status` text NOT NULL,
	`result_json` text DEFAULT '{}' NOT NULL,
	`created_at` text NOT NULL,
	FOREIGN KEY (`inference_run_id`) REFERENCES `inference_runs`(`id`) ON UPDATE no action ON DELETE cascade,
	FOREIGN KEY (`frame_id`) REFERENCES `frames`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE INDEX `idx_frame_predictions_run` ON `frame_predictions` (`inference_run_id`,`frame_id`);--> statement-breakpoint
CREATE INDEX `idx_frame_predictions_track` ON `frame_predictions` (`track_id`,`created_at`);--> statement-breakpoint
CREATE TABLE `frames` (
	`id` text PRIMARY KEY NOT NULL,
	`video_asset_id` text NOT NULL,
	`capture_session_id` text NOT NULL,
	`frame_index` integer NOT NULL,
	`timestamp_ms` integer NOT NULL,
	`object_key` text,
	`quality_score` real,
	`processing_status` text NOT NULL,
	`created_at` text NOT NULL,
	FOREIGN KEY (`video_asset_id`) REFERENCES `video_assets`(`id`) ON UPDATE no action ON DELETE cascade,
	FOREIGN KEY (`capture_session_id`) REFERENCES `capture_sessions`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE UNIQUE INDEX `frames_object_key_unique` ON `frames` (`object_key`);--> statement-breakpoint
CREATE UNIQUE INDEX `uq_frames_video_index` ON `frames` (`video_asset_id`,`frame_index`);--> statement-breakpoint
CREATE INDEX `idx_frames_session_time` ON `frames` (`capture_session_id`,`timestamp_ms`);--> statement-breakpoint
CREATE TABLE `houses` (
	`id` text PRIMARY KEY NOT NULL,
	`farm_id` text NOT NULL,
	`code` text NOT NULL,
	`name` text NOT NULL,
	`display_order` integer DEFAULT 0 NOT NULL,
	`status` text DEFAULT 'ACTIVE' NOT NULL,
	`metadata_json` text DEFAULT '{}' NOT NULL,
	`created_at` text NOT NULL,
	`updated_at` text NOT NULL,
	FOREIGN KEY (`farm_id`) REFERENCES `farms`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE UNIQUE INDEX `uq_houses_farm_code` ON `houses` (`farm_id`,`code`);--> statement-breakpoint
CREATE INDEX `idx_houses_farm_order` ON `houses` (`farm_id`,`display_order`);--> statement-breakpoint
CREATE TABLE `inference_runs` (
	`id` text PRIMARY KEY NOT NULL,
	`capture_session_id` text NOT NULL,
	`task` text NOT NULL,
	`model_version` text NOT NULL,
	`status` text NOT NULL,
	`started_at` text NOT NULL,
	`finished_at` text,
	`created_at` text NOT NULL,
	FOREIGN KEY (`capture_session_id`) REFERENCES `capture_sessions`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE INDEX `idx_inference_runs_session_task` ON `inference_runs` (`capture_session_id`,`task`);--> statement-breakpoint
CREATE TABLE `video_assets` (
	`id` text PRIMARY KEY NOT NULL,
	`capture_session_id` text NOT NULL,
	`camera_id` text,
	`modality` text NOT NULL,
	`object_key` text,
	`original_name` text,
	`source_uri` text,
	`duration_ms` integer,
	`frame_rate` real,
	`frame_count` integer,
	`processing_status` text NOT NULL,
	`created_at` text NOT NULL,
	FOREIGN KEY (`capture_session_id`) REFERENCES `capture_sessions`(`id`) ON UPDATE no action ON DELETE cascade,
	FOREIGN KEY (`camera_id`) REFERENCES `cameras`(`id`) ON UPDATE no action ON DELETE set null
);
--> statement-breakpoint
CREATE UNIQUE INDEX `video_assets_object_key_unique` ON `video_assets` (`object_key`);--> statement-breakpoint
CREATE INDEX `idx_video_assets_session` ON `video_assets` (`capture_session_id`,`modality`);--> statement-breakpoint
CREATE TABLE `zones` (
	`id` text PRIMARY KEY NOT NULL,
	`bed_id` text NOT NULL,
	`code` text NOT NULL,
	`name` text NOT NULL,
	`display_order` integer DEFAULT 0 NOT NULL,
	`status` text DEFAULT 'ACTIVE' NOT NULL,
	`metadata_json` text DEFAULT '{}' NOT NULL,
	`created_at` text NOT NULL,
	`updated_at` text NOT NULL,
	FOREIGN KEY (`bed_id`) REFERENCES `beds`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE UNIQUE INDEX `uq_zones_bed_code` ON `zones` (`bed_id`,`code`);--> statement-breakpoint
CREATE INDEX `idx_zones_bed_order` ON `zones` (`bed_id`,`display_order`);