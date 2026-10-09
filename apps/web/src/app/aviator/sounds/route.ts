import { readdir } from 'node:fs/promises';
import path from 'node:path';

export const dynamic = 'force-dynamic';

/**
 * GET /aviator/sounds — which optional sound files are in public/aviator/sounds,
 * so the game only fetches files that exist (no 404s in players' consoles).
 */
export async function GET() {
  let files: string[] = [];
  try {
    files = (await readdir(path.join(process.cwd(), 'public', 'aviator', 'sounds'))).filter((f) => f.endsWith('.mp3'));
  } catch { /* folder missing: no files */ }
  return Response.json({ files }, { headers: { 'Cache-Control': 'public, max-age=300' } });
}
