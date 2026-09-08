import { receivePestCapture } from '../pest-capture/route';
export const runtime = 'edge';
// Preserve old uploads that do not submit a target.
export async function POST(request: Request) { return receivePestCapture(request, 'MITE'); }
