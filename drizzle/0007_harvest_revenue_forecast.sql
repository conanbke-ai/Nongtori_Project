CREATE INDEX IF NOT EXISTS `idx_capture_sessions_farm_item_started` ON `capture_sessions` (`farm_id`,`item_id`,`started_at`);--> statement-breakpoint
CREATE TABLE IF NOT EXISTS `harvest_runs` (
	`id` text PRIMARY KEY NOT NULL,
	`farm_id` text NOT NULL,
	`item_id` text NOT NULL,
	`camera_id` text,
	`status` text NOT NULL,
	`started_at` text NOT NULL,
	`completed_at` text,
	`started_by_member_id` text,
	`started_by_name_snapshot` text,
	`completed_by_member_id` text,
	`completed_by_name_snapshot` text,
	`note` text DEFAULT '' NOT NULL,
	`harvested_count` integer DEFAULT 0 NOT NULL,
	`total_weight_g` real DEFAULT 0 NOT NULL,
	`created_at` text NOT NULL,
	`updated_at` text NOT NULL,
	FOREIGN KEY (`farm_id`) REFERENCES `farms`(`id`) ON UPDATE no action ON DELETE cascade,
	FOREIGN KEY (`item_id`) REFERENCES `farm_items`(`id`) ON UPDATE no action ON DELETE restrict,
	FOREIGN KEY (`camera_id`) REFERENCES `cameras`(`id`) ON UPDATE no action ON DELETE set null,
	FOREIGN KEY (`started_by_member_id`) REFERENCES `farm_members`(`id`) ON UPDATE no action ON DELETE set null,
	FOREIGN KEY (`completed_by_member_id`) REFERENCES `farm_members`(`id`) ON UPDATE no action ON DELETE set null
);--> statement-breakpoint
CREATE INDEX IF NOT EXISTS `idx_harvest_runs_farm_completed` ON `harvest_runs` (`farm_id`,`completed_at`);--> statement-breakpoint
CREATE INDEX IF NOT EXISTS `idx_harvest_runs_item_status_completed` ON `harvest_runs` (`item_id`,`status`,`completed_at`);--> statement-breakpoint
CREATE TABLE IF NOT EXISTS `harvest_grade_summaries` (
	`id` text PRIMARY KEY NOT NULL,
	`harvest_run_id` text NOT NULL,
	`grade_code` text NOT NULL,
	`fruit_count` integer NOT NULL,
	`total_weight_g` real NOT NULL,
	`average_confidence` real,
	`created_at` text NOT NULL,
	FOREIGN KEY (`harvest_run_id`) REFERENCES `harvest_runs`(`id`) ON UPDATE no action ON DELETE cascade
);--> statement-breakpoint
CREATE UNIQUE INDEX IF NOT EXISTS `uq_harvest_grade_run_grade` ON `harvest_grade_summaries` (`harvest_run_id`,`grade_code`);--> statement-breakpoint
CREATE TABLE IF NOT EXISTS `price_forecasts` (
	`id` text PRIMARY KEY NOT NULL,
	`crop_code` text NOT NULL,
	`cultivar_code` text,
	`grade_code` text NOT NULL,
	`target_date` text NOT NULL,
	`horizon_days` integer NOT NULL,
	`model_name` text NOT NULL,
	`model_version` text NOT NULL,
	`price_p10_per_kg` real NOT NULL,
	`price_p50_per_kg` real NOT NULL,
	`price_p90_per_kg` real NOT NULL,
	`feature_snapshot_json` text DEFAULT '{}' NOT NULL,
	`status` text NOT NULL,
	`generated_at` text NOT NULL,
	FOREIGN KEY (`crop_code`) REFERENCES `crop_types`(`code`) ON UPDATE no action ON DELETE cascade,
	FOREIGN KEY (`cultivar_code`) REFERENCES `cultivars`(`code`) ON UPDATE no action ON DELETE set null
);--> statement-breakpoint
CREATE INDEX IF NOT EXISTS `idx_price_forecasts_series_target` ON `price_forecasts` (`crop_code`,`cultivar_code`,`grade_code`,`target_date`);--> statement-breakpoint
CREATE TABLE IF NOT EXISTS `revenue_forecasts` (
	`id` text PRIMARY KEY NOT NULL,
	`harvest_run_id` text NOT NULL,
	`grade_breakdown_json` text NOT NULL,
	`estimated_gross_won` real NOT NULL,
	`estimated_cost_won` real DEFAULT 0 NOT NULL,
	`estimated_net_won` real NOT NULL,
	`revenue_p10_won` real,
	`revenue_p90_won` real,
	`price_basis_date` text NOT NULL,
	`price_model_name` text NOT NULL,
	`price_model_version` text NOT NULL,
	`status` text NOT NULL,
	`generated_at` text NOT NULL,
	FOREIGN KEY (`harvest_run_id`) REFERENCES `harvest_runs`(`id`) ON UPDATE no action ON DELETE cascade
);--> statement-breakpoint
CREATE UNIQUE INDEX IF NOT EXISTS `uq_revenue_forecasts_harvest_run` ON `revenue_forecasts` (`harvest_run_id`);--> statement-breakpoint
CREATE INDEX IF NOT EXISTS `idx_revenue_forecasts_status_generated` ON `revenue_forecasts` (`status`,`generated_at`);--> statement-breakpoint
CREATE TABLE IF NOT EXISTS `forecast_jobs` (
	`id` text PRIMARY KEY NOT NULL,
	`harvest_run_id` text NOT NULL,
	`job_type` text NOT NULL,
	`status` text NOT NULL,
	`attempts` integer DEFAULT 0 NOT NULL,
	`last_error` text,
	`created_at` text NOT NULL,
	`updated_at` text NOT NULL,
	FOREIGN KEY (`harvest_run_id`) REFERENCES `harvest_runs`(`id`) ON UPDATE no action ON DELETE cascade
);--> statement-breakpoint
CREATE UNIQUE INDEX IF NOT EXISTS `uq_forecast_jobs_run_type` ON `forecast_jobs` (`harvest_run_id`,`job_type`);--> statement-breakpoint
CREATE INDEX IF NOT EXISTS `idx_forecast_jobs_status_created` ON `forecast_jobs` (`status`,`created_at`);--> statement-breakpoint
CREATE TABLE IF NOT EXISTS `forecast_model_registry` (
	`id` text PRIMARY KEY NOT NULL,
	`model_name` text NOT NULL,
	`model_version` text NOT NULL,
	`algorithm` text NOT NULL,
	`status` text NOT NULL,
	`training_started_at` text,
	`training_ended_at` text,
	`metrics_json` text DEFAULT '{}' NOT NULL,
	`artifact_uri` text,
	`deployed_at` text,
	`created_at` text NOT NULL
);--> statement-breakpoint
CREATE UNIQUE INDEX IF NOT EXISTS `uq_forecast_model_name_version` ON `forecast_model_registry` (`model_name`,`model_version`);--> statement-breakpoint
CREATE INDEX IF NOT EXISTS `idx_forecast_model_status` ON `forecast_model_registry` (`status`,`deployed_at`);
--> statement-breakpoint
CREATE TABLE IF NOT EXISTS `farm_revenue_settings` (
	`id` text PRIMARY KEY NOT NULL,
	`farm_id` text NOT NULL,
	`item_id` text NOT NULL,
	`commission_rate` real DEFAULT 0 NOT NULL,
	`packaging_won_per_kg` real DEFAULT 0 NOT NULL,
	`labor_won_per_kg` real DEFAULT 0 NOT NULL,
	`shipping_won_per_kg` real DEFAULT 0 NOT NULL,
	`status` text DEFAULT 'ACTIVE' NOT NULL,
	`updated_at` text NOT NULL,
	FOREIGN KEY (`farm_id`) REFERENCES `farms`(`id`) ON UPDATE no action ON DELETE cascade,
	FOREIGN KEY (`item_id`) REFERENCES `farm_items`(`id`) ON UPDATE no action ON DELETE cascade
);--> statement-breakpoint
CREATE UNIQUE INDEX IF NOT EXISTS `uq_farm_revenue_settings_item` ON `farm_revenue_settings` (`farm_id`,`item_id`);--> statement-breakpoint
CREATE INDEX IF NOT EXISTS `idx_farm_revenue_settings_status` ON `farm_revenue_settings` (`farm_id`,`status`);
