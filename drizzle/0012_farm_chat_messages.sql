CREATE TABLE `farm_chat_messages` (
	`id` text PRIMARY KEY NOT NULL,
	`farm_id` text NOT NULL,
	`author_member_id` text,
	`author_name_snapshot` text NOT NULL,
	`author_role_snapshot` text NOT NULL,
	`author_account_snapshot` text NOT NULL,
	`language` text DEFAULT 'ko' NOT NULL,
	`content` text NOT NULL,
	`status` text DEFAULT 'ACTIVE' NOT NULL,
	`created_at` text NOT NULL,
	`updated_at` text NOT NULL,
	FOREIGN KEY (`farm_id`) REFERENCES `farms`(`id`) ON UPDATE no action ON DELETE cascade,
	FOREIGN KEY (`author_member_id`) REFERENCES `farm_members`(`id`) ON UPDATE no action ON DELETE set null,
	CONSTRAINT `ck_farm_chat_messages_language` CHECK(`language` in ('ko', 'vi', 'th', 'zh-CN')),
	CONSTRAINT `ck_farm_chat_messages_status` CHECK(`status` in ('ACTIVE', 'DELETED')),
	CONSTRAINT `ck_farm_chat_messages_content_length` CHECK(length(`content`) between 1 and 500)
);
--> statement-breakpoint
CREATE INDEX `idx_farm_chat_messages_farm_status_created`
ON `farm_chat_messages` (`farm_id`,`status`,`created_at`);
--> statement-breakpoint
CREATE INDEX `idx_farm_chat_messages_author_created`
ON `farm_chat_messages` (`author_member_id`,`created_at`);
--> statement-breakpoint
PRAGMA optimize;
