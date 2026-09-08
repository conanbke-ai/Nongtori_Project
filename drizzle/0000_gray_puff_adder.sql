CREATE TABLE `assets` (
	`id` text PRIMARY KEY NOT NULL,
	`observation_id` text NOT NULL,
	`modality` text NOT NULL,
	`object_key` text NOT NULL,
	`original_name` text NOT NULL,
	`content_type` text NOT NULL,
	`size_bytes` integer NOT NULL,
	`created_at` text NOT NULL,
	FOREIGN KEY (`observation_id`) REFERENCES `observations`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE UNIQUE INDEX `assets_object_key_unique` ON `assets` (`object_key`);--> statement-breakpoint
CREATE INDEX `idx_assets_observation` ON `assets` (`observation_id`);--> statement-breakpoint
CREATE TABLE `observations` (
	`id` text PRIMARY KEY NOT NULL,
	`farm_id` text NOT NULL,
	`house_id` text NOT NULL,
	`bed_id` text NOT NULL,
	`zone_id` text NOT NULL,
	`plant_id` text,
	`leaf_id` text,
	`cultivar` text NOT NULL,
	`pest_species` text NOT NULL,
	`capture_at` text NOT NULL,
	`visual_symptom_status` text NOT NULL,
	`active_pest_status` text NOT NULL,
	`decision_status` text NOT NULL,
	`environment_status` text NOT NULL,
	`processing_status` text NOT NULL,
	`created_at` text NOT NULL
);
--> statement-breakpoint
CREATE INDEX `idx_observations_zone_capture` ON `observations` (`farm_id`,`house_id`,`bed_id`,`zone_id`,`capture_at`);--> statement-breakpoint
CREATE INDEX `idx_observations_processing` ON `observations` (`processing_status`,`created_at`);