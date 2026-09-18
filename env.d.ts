declare namespace Cloudflare {
  interface Env {
    DB: D1Database;
    FILES: R2Bucket;

    GOOGLE_TRANSLATE_API_KEY?: string;

    SMS_VERIFICATION_URL?: string;
    SMS_VERIFICATION_TOKEN?: string;
    PHONE_VERIFICATION_PEPPER?: string;

    NOTIFICATION_WORKER_TOKEN?: string;
    SMS_ALERT_URL?: string;
    SMS_ALERT_TOKEN?: string;

    FORECAST_WORKER_TOKEN?: string;
    ROBOT_INGEST_TOKEN?: string;
    VENDOR_IMPORT_TOKEN?: string;
  }
}
