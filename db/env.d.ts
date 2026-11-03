declare namespace Cloudflare {
  interface Env {
    DB: D1Database;
    SCOUTING_MUTATION_IDEMPOTENCY?: string;
    SCOUTING_RECEIPT_FARM_LIMIT?: string;
    SCOUTING_RECEIPT_MEMBER_LIMIT?: string;
  }
}
