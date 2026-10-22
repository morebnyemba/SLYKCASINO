/**
 * Code 39 barcodes for ticket codes: the classic retail barcode, read by
 * phone scanner apps and the browser's BarcodeDetector. Ticket codes only use
 * A–Z and 2–9, all in Code 39's set.
 *
 * Each character is 9 elements, bar/space alternating from a bar; 1 = wide.
 */
const PATTERNS: Record<string, string> = {
  '0': '000110100', '1': '100100001', '2': '001100001', '3': '101100000', '4': '000110001',
  '5': '100110000', '6': '001110000', '7': '000100101', '8': '100100100', '9': '001100100',
  A: '100001001', B: '001001001', C: '101001000', D: '000011001', E: '100011000', F: '001011000',
  G: '000001101', H: '100001100', I: '001001100', J: '000011100', K: '100000011', L: '001000011',
  M: '101000010', N: '000010011', O: '100010010', P: '001010010', Q: '000000111', R: '100000110',
  S: '001000110', T: '000010110', U: '110000001', V: '011000001', W: '111000000', X: '010010001',
  Y: '110010000', Z: '011010000', '-': '010000101', '.': '110000100', ' ': '011000100', '*': '010010100',
};

const WIDE = 3;

/** The bars of `text` as [x, width] in narrow-bar units, plus the total width (quiet zones excluded). */
export function code39Bars(text: string): { bars: [number, number][]; width: number } {
  const chars = `*${text.toUpperCase()}*`;
  const bars: [number, number][] = [];
  let x = 0;
  for (const [i, ch] of [...chars].entries()) {
    const pattern = PATTERNS[ch];
    if (!pattern) throw new Error(`Code 39 can't encode "${ch}"`);
    for (let e = 0; e < 9; e++) {
      const w = pattern[e] === '1' ? WIDE : 1;
      if (e % 2 === 0) bars.push([x, w]);
      x += w;
    }
    if (i < chars.length - 1) x += 1; // narrow gap between characters
  }
  return { bars, width: x };
}
