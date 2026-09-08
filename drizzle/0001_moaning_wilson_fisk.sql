PRAGMA foreign_keys=OFF;--> statement-breakpoint
CREATE TABLE `__new_observations` (
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
	`created_at` text NOT NULL,
	CONSTRAINT "observations_cultivar_check" CHECK("__new_observations"."cultivar" = 'SEOLHYANG')
);
--> statement-breakpoint
INSERT INTO `__new_observations`("id", "farm_id", "house_id", "bed_id", "zone_id", "plant_id", "leaf_id", "cultivar", "pest_species", "capture_at", "visual_symptom_status", "active_pest_status", "decision_status", "environment_status", "processing_status", "created_at") SELECT "id", "farm_id", "house_id", "bed_id", "zone_id", "plant_id", "leaf_id", "cultivar", "pest_species", "capture_at", "visual_symptom_status", "active_pest_status", "decision_status", "environment_status", "processing_status", "created_at" FROM `observations`;--> statement-breakpoint
DROP TABLE `observations`;--> statement-breakpoint
ALTER TABLE `__new_observations` RENAME TO `observations`;--> statement-breakpoint
PRAGMA foreign_keys=ON;--> statement-breakpoint
CREATE INDEX `idx_observations_zone_capture` ON `observations` (`farm_id`,`house_id`,`bed_id`,`zone_id`,`capture_at`);--> statement-breakpoint
CREATE INDEX `idx_observations_processing` ON `observations` (`processing_status`,`created_at`);