UPDATE `farm_members`
SET `approved_at` = COALESCE(`approved_at`, `joined_at`, `created_at`, `updated_at`),
    `joined_at` = COALESCE(`joined_at`, `approved_at`, `created_at`, `updated_at`)
WHERE `status` = 'ACTIVE' AND `approved_at` IS NULL;
--> statement-breakpoint
PRAGMA optimize;
