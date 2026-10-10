import { readFile } from 'node:fs/promises';
import path from 'node:path';

/** A file from public/brand as a data URL, for the generated link-preview images (null if missing). */
export async function brandDataUrl(file: 'mark.png' | 'wordmark.png'): Promise<string | null> {
  try {
    const data = await readFile(path.join(process.cwd(), 'public', 'brand', file));
    return `data:image/png;base64,${data.toString('base64')}`;
  } catch {
    return null;
  }
}
