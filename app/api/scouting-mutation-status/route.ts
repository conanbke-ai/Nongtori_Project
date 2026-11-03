import { handleScoutingIntentLookup } from '@/app/api/_lib/scouting-idempotency';

export const runtime = 'edge';

// Explicit user-initiated read-only POST keeps key/intent out of URLs.
// It is not another mutation attempt and performs no bootstrap or writes.
export async function POST(request: Request) {
  return handleScoutingIntentLookup(request);
}
