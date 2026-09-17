import { env } from 'cloudflare:workers';

let notificationReady: Promise<void> | undefined;

const statements = [
  `CREATE TABLE IF NOT EXISTS app_notifications (
    id TEXT PRIMARY KEY NOT NULL,
    farm_id TEXT NOT NULL,
    category TEXT NOT NULL,
    notification_type TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'INFO',
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    entity_type TEXT,
    entity_id TEXT,
    location_state_id TEXT,
    case_id TEXT,
    deep_link_screen TEXT,
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY (farm_id) REFERENCES farms(id) ON DELETE CASCADE
  )`,
  `CREATE INDEX IF NOT EXISTS idx_app_notifications_farm_created
    ON app_notifications(farm_id, created_at)`,
  `CREATE INDEX IF NOT EXISTS idx_app_notifications_location_created
    ON app_notifications(location_state_id, created_at)`,
  `CREATE TABLE IF NOT EXISTS app_notification_recipients (
    id TEXT PRIMARY KEY NOT NULL,
    notification_id TEXT NOT NULL,
    recipient_member_id TEXT NOT NULL,
    read_at TEXT,
    dismissed_at TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (notification_id) REFERENCES app_notifications(id) ON DELETE CASCADE,
    FOREIGN KEY (recipient_member_id) REFERENCES farm_members(id) ON DELETE CASCADE,
    UNIQUE(notification_id, recipient_member_id)
  )`,
  `CREATE INDEX IF NOT EXISTS idx_app_notification_recipients_member_created
    ON app_notification_recipients(recipient_member_id, created_at)`,
  `CREATE INDEX IF NOT EXISTS idx_app_notification_recipients_member_unread
    ON app_notification_recipients(recipient_member_id, read_at, dismissed_at, created_at)`,
];

export function ensureNotificationRuntime() {
  if (!env.DB) throw new Error('Cloudflare D1 binding `DB` is unavailable.');
  const pending = notificationReady ??= env.DB.batch(statements.map((sql) => env.DB.prepare(sql))).then(() => undefined);
  return pending.catch((error) => {
    if (notificationReady === pending) notificationReady = undefined;
    throw error;
  });
}
