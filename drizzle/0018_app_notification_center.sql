-- Generic in-app notification center.
-- External delivery remains in notification_outbox; read/dismiss state lives here.

CREATE TABLE IF NOT EXISTS `app_notifications` (
  `id` text PRIMARY KEY NOT NULL,
  `farm_id` text NOT NULL,
  `category` text NOT NULL,
  `notification_type` text NOT NULL,
  `severity` text NOT NULL DEFAULT 'INFO',
  `title` text NOT NULL,
  `body` text NOT NULL,
  `entity_type` text,
  `entity_id` text,
  `location_state_id` text,
  `case_id` text,
  `deep_link_screen` text,
  `payload_json` text NOT NULL DEFAULT '{}',
  `created_at` text NOT NULL,
  FOREIGN KEY (`farm_id`) REFERENCES `farms`(`id`) ON DELETE CASCADE,
  CHECK (`category` IN ('PEST', 'HARVEST', 'ENVIRONMENT', 'SYSTEM', 'MARKET', 'OTHER')),
  CHECK (`severity` IN ('INFO', 'NOTICE', 'WARNING', 'CRITICAL'))
);
CREATE INDEX IF NOT EXISTS `idx_app_notifications_farm_created`
  ON `app_notifications` (`farm_id`, `created_at`);
CREATE INDEX IF NOT EXISTS `idx_app_notifications_location_created`
  ON `app_notifications` (`location_state_id`, `created_at`);

CREATE TABLE IF NOT EXISTS `app_notification_recipients` (
  `id` text PRIMARY KEY NOT NULL,
  `notification_id` text NOT NULL,
  `recipient_member_id` text NOT NULL,
  `read_at` text,
  `dismissed_at` text,
  `created_at` text NOT NULL,
  FOREIGN KEY (`notification_id`) REFERENCES `app_notifications`(`id`) ON DELETE CASCADE,
  FOREIGN KEY (`recipient_member_id`) REFERENCES `farm_members`(`id`) ON DELETE CASCADE,
  UNIQUE (`notification_id`, `recipient_member_id`)
);
CREATE INDEX IF NOT EXISTS `idx_app_notification_recipients_member_created`
  ON `app_notification_recipients` (`recipient_member_id`, `created_at`);
CREATE INDEX IF NOT EXISTS `idx_app_notification_recipients_member_unread`
  ON `app_notification_recipients` (`recipient_member_id`, `read_at`, `dismissed_at`, `created_at`);
