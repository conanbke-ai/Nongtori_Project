ALTER TABLE `observations` ADD `capture_method` text DEFAULT 'PAIRED_STILL' NOT NULL;--> statement-breakpoint
ALTER TABLE `observations` ADD `pairing_id` text DEFAULT 'LEGACY' NOT NULL;--> statement-breakpoint
ALTER TABLE `observations` ADD `source_video_id` text;--> statement-breakpoint
ALTER TABLE `observations` ADD `rgb_frame_index` integer;--> statement-breakpoint
ALTER TABLE `observations` ADD `thermal_frame_index` integer;