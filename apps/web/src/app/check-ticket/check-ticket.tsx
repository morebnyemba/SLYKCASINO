'use client';

import { useRouter } from 'next/navigation';
import { useEffect, useRef, useState } from 'react';
import { BsCameraVideo, BsUpcScan, BsXLg } from 'react-icons/bs';

const ALPHABET = /^[ABCDEFGHJKMNPQRSTUVWXYZ23456789]{10}$/;

/** A ticket code from what was typed, pasted (even a whole ticket link) or scanned. */
function readCode(raw: string): string | null {
  const fromLink = raw.match(/\/ticket\/([A-Za-z0-9-]+)/);
  const code = (fromLink ? fromLink[1] : raw).toUpperCase().replace(/[^A-Z0-9]/g, '');
  return ALPHABET.test(code) ? code : null;
}

interface Detector { detect: (source: CanvasImageSource) => Promise<{ rawValue: string }[]> }
type DetectorCtor = new (opts: { formats: string[] }) => Detector;

/** Point the camera at a ticket's barcode (browsers with BarcodeDetector: Chrome on Android, Safari 17+). */
function Scanner({ onCode, onClose }: { onCode: (code: string) => void; onClose: () => void }) {
  const video = useRef<HTMLVideoElement>(null);
  const [error, setError] = useState('');
  // The latest callback, so a re-render doesn't restart the camera.
  const onCodeRef = useRef(onCode);
  onCodeRef.current = onCode;

  useEffect(() => {
    let stream: MediaStream | null = null;
    let timer = 0;
    let stopped = false;
    const Ctor = (window as unknown as { BarcodeDetector?: DetectorCtor }).BarcodeDetector!;
    const detector = new Ctor({ formats: ['code_39', 'qr_code'] });
    (async () => {
      try {
        stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' }, audio: false });
        if (stopped || !video.current) return;
        video.current.srcObject = stream;
        await video.current.play();
        const tick = async () => {
          if (stopped || !video.current) return;
          try {
            for (const hit of await detector.detect(video.current)) {
              const code = readCode(hit.rawValue);
              if (code) { onCodeRef.current(code); return; }
            }
          } catch { /* frame not ready */ }
          timer = window.setTimeout(tick, 250);
        };
        void tick();
      } catch {
        setError('We couldn’t use the camera. Allow camera access, or type the code instead.');
      }
    })();
    return () => { stopped = true; window.clearTimeout(timer); stream?.getTracks().forEach((t) => t.stop()); };
  }, []);

  return (
    <div className="space-y-3">
      <div className="relative overflow-hidden rounded-2xl bg-black">
        <video ref={video} playsInline muted className="aspect-[4/3] w-full object-cover" />
        {/* Aim here */}
        <div className="pointer-events-none absolute inset-x-8 top-1/2 h-20 -translate-y-1/2 rounded-lg border-2 border-white/80 shadow-[0_0_0_9999px_rgba(0,0,0,0.35)]" />
        <button onClick={onClose} aria-label="Stop scanning" className="absolute right-2 top-2 rounded-full bg-black/60 p-2 text-white">
          <BsXLg size={13} />
        </button>
      </div>
      <p className="text-center text-xs text-muted-foreground">{error || 'Hold the barcode inside the box.'}</p>
    </div>
  );
}

/** "Check a ticket": by its code, typed or scanned from the barcode. */
export function CheckTicket() {
  const router = useRouter();
  const [value, setValue] = useState('');
  const [error, setError] = useState('');
  const [scanning, setScanning] = useState(false);
  const [canScan, setCanScan] = useState(false);
  useEffect(() => { setCanScan('BarcodeDetector' in window && !!navigator.mediaDevices?.getUserMedia); }, []);

  function go(raw: string) {
    const code = readCode(raw);
    if (!code) { setError('A ticket code is 10 letters and numbers, printed under the barcode (e.g. K7PQ2 MXH9D).'); return; }
    router.push(`/ticket/${code}`);
  }

  return (
    <div className="mx-auto max-w-md space-y-5 py-2">
      <div className="text-center">
        <span className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-2xl bg-secondary/15 text-secondary"><BsUpcScan size={22} /></span>
        <h1 className="text-2xl font-extrabold">Check a ticket</h1>
        <p className="mt-1 text-sm text-muted-foreground">See any ticket’s selections, live scores and result from its code.</p>
      </div>

      {scanning ? (
        <Scanner onCode={(code) => router.push(`/ticket/${code}`)} onClose={() => setScanning(false)} />
      ) : (
        <form onSubmit={(e) => { e.preventDefault(); go(value); }} className="space-y-3 rounded-2xl border border-border bg-card p-4">
          <label className="block space-y-1.5">
            <span className="text-sm font-semibold">Ticket code</span>
            <input
              value={value}
              onChange={(e) => { setValue(e.target.value.toUpperCase()); setError(''); }}
              placeholder="K7PQ2 MXH9D"
              autoCapitalize="characters" autoComplete="off" spellCheck={false} inputMode="text"
              className="w-full rounded-xl border border-border bg-input px-3 py-3 text-center font-mono text-lg font-bold tracking-[0.25em] outline-none focus:ring-2 focus:ring-ring"
            />
          </label>
          {error && <p className="text-sm text-destructive">{error}</p>}
          <button type="submit" className="w-full rounded-xl bg-win py-3 text-sm font-extrabold text-win-foreground">Check ticket</button>
          {canScan ? (
            <button type="button" onClick={() => setScanning(true)}
              className="flex w-full items-center justify-center gap-2 rounded-xl border border-border py-3 text-sm font-bold hover:bg-muted">
              <BsCameraVideo size={15} /> Scan the barcode
            </button>
          ) : (
            <p className="text-center text-xs text-muted-foreground">The code is printed under the ticket’s barcode.</p>
          )}
        </form>
      )}
    </div>
  );
}
