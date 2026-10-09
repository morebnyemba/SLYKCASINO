'use client';

import { useEffect, useRef, useState } from 'react';
import { fmtX, multiplierAt, type JetRound } from '@/lib/jet';

const RED = '#e50539';

/** A red propeller plane, nose right, drawn around (0, 0); `spin` turns the prop. */
function drawPlane(ctx: CanvasRenderingContext2D, scale: number, spin: number) {
  ctx.save();
  ctx.scale(scale, scale);
  ctx.fillStyle = RED;
  // fuselage
  ctx.beginPath();
  ctx.moveTo(30, -3);
  ctx.quadraticCurveTo(32, 0, 30, 4);
  ctx.lineTo(-18, 6);
  ctx.quadraticCurveTo(-30, 4, -34, -2);
  ctx.lineTo(-30, -6);
  ctx.lineTo(4, -8);
  ctx.quadraticCurveTo(24, -8, 30, -3);
  ctx.fill();
  // tail fin and stabiliser
  ctx.beginPath();
  ctx.moveTo(-26, -5); ctx.lineTo(-36, -20); ctx.lineTo(-30, -20); ctx.lineTo(-16, -6); ctx.closePath(); ctx.fill();
  ctx.beginPath();
  ctx.moveTo(-24, 2); ctx.lineTo(-38, 6); ctx.lineTo(-34, 9); ctx.lineTo(-20, 5); ctx.closePath(); ctx.fill();
  // main wing (slight perspective)
  ctx.fillStyle = '#b8032d';
  ctx.beginPath();
  ctx.moveTo(10, 0); ctx.lineTo(-8, 22); ctx.lineTo(-16, 22); ctx.lineTo(-6, 0); ctx.closePath(); ctx.fill();
  ctx.fillStyle = RED;
  ctx.beginPath();
  ctx.moveTo(10, -4); ctx.lineTo(-2, -14); ctx.lineTo(-9, -14); ctx.lineTo(-4, -4); ctx.closePath(); ctx.fill();
  // cockpit window
  ctx.fillStyle = 'rgba(255,255,255,0.85)';
  ctx.beginPath();
  ctx.moveTo(8, -8); ctx.quadraticCurveTo(14, -15, 20, -8); ctx.closePath(); ctx.fill();
  // nose cap + spinning propeller
  ctx.fillStyle = '#ff2b5e';
  ctx.beginPath(); ctx.arc(31, 0.5, 3.2, 0, Math.PI * 2); ctx.fill();
  const blade = Math.abs(Math.cos(spin)) * 16 + 2;
  ctx.fillStyle = 'rgba(255,255,255,0.55)';
  ctx.beginPath(); ctx.ellipse(34, 0.5, 2, blade, 0, 0, Math.PI * 2); ctx.fill();
  ctx.restore();
}

/** The plane artwork from the purchased game package (nose up and to the right). */
const PLANE_SRC = '/aviator/plane.png';
// Where the plane's tail sits in the image, as a fraction of its size — the
// curve's tip is drawn there so the plane looks like it's pulling the line.
const TAIL = { x: 0.1, y: 0.78 };

function drawPlaneImage(ctx: CanvasRenderingContext2D, img: HTMLImageElement, tipX: number, tipY: number, width: number, tilt: number) {
  const height = width * (img.naturalHeight / img.naturalWidth);
  ctx.save();
  ctx.translate(tipX, tipY);
  ctx.rotate(tilt);
  ctx.drawImage(img, -width * TAIL.x, -height * TAIL.y, width, height);
  ctx.restore();
}

/** A big two-blade propeller for the waiting screen. */
function drawPropeller(ctx: CanvasRenderingContext2D, x: number, y: number, r: number, angle: number) {
  ctx.save();
  ctx.translate(x, y);
  ctx.rotate(angle);
  ctx.fillStyle = RED;
  for (const dir of [1, -1]) {
    ctx.beginPath();
    ctx.moveTo(0, 0);
    ctx.quadraticCurveTo(r * 0.35 * dir, -r * 0.18, r * dir, -r * 0.08);
    ctx.quadraticCurveTo(r * 1.04 * dir, 0, r * dir, r * 0.08);
    ctx.quadraticCurveTo(r * 0.35 * dir, r * 0.18, 0, 0);
    ctx.fill();
  }
  ctx.fillStyle = '#ff2b5e';
  ctx.beginPath(); ctx.arc(0, 0, r * 0.16, 0, Math.PI * 2); ctx.fill();
  ctx.restore();
}

/**
 * The flight, Aviator-style: a dark sky with slowly turning rays, the red
 * climbing curve and the plane on its tip, the multiplier on top. Everything
 * comes from the server clock (`now`) and the round's start time, so every
 * player sees the same flight.
 */
export function FlightScene({ round, rate, bettingSeconds, now }: {
  round: JetRound | null; rate: number; bettingSeconds: number; now: () => number;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const roundRef = useRef(round);
  roundRef.current = round;
  const [label, setLabel] = useState<{ big: string; small: string; tone: 'fly' | 'crash' | 'wait' | 'idle'; progress: number }>(
    { big: '', small: '', tone: 'idle', progress: 0 },
  );

  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext('2d');
    if (!canvas || !ctx) return;
    let raf = 0;
    let lastLabel = '';
    const plane = new Image();
    plane.src = PLANE_SRC;
    const planeReady = () => plane.complete && plane.naturalWidth > 0;
    // Plane width on screen: about 190px on a wide game, smaller on phones.
    const planeWidth = (w: number, h: number) => Math.max(110, Math.min(200, Math.min(w / 3.8, h / 1.9)));
    let crashSeenAt = 0;
    let crashId = 0;

    const frame = () => {
      const r = roundRef.current;
      const dpr = window.devicePixelRatio || 1;
      const w = canvas.clientWidth;
      const h = canvas.clientHeight;
      if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) {
        canvas.width = Math.round(w * dpr);
        canvas.height = Math.round(h * dpr);
      }
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      const t = now();

      // Sky: near-black with grey rays turning around the bottom-left corner.
      ctx.fillStyle = '#0c0c0e';
      ctx.fillRect(0, 0, w, h);
      const flying = r?.status === 'flying';
      ctx.save();
      ctx.translate(0, h);
      ctx.rotate(flying ? (t / 9000) % (Math.PI * 2) : 0);
      const reach = Math.hypot(w, h) * 1.3;
      for (let i = 0; i < 36; i += 2) {
        const a0 = (i / 36) * Math.PI * 2;
        const a1 = ((i + 1) / 36) * Math.PI * 2;
        const g = ctx.createRadialGradient(0, 0, 0, 0, 0, reach);
        g.addColorStop(0, 'rgba(255,255,255,0.05)');
        g.addColorStop(1, 'rgba(255,255,255,0.012)');
        ctx.fillStyle = g;
        ctx.beginPath(); ctx.moveTo(0, 0); ctx.arc(0, 0, reach, a0, a1); ctx.closePath(); ctx.fill();
      }
      ctx.restore();

      const padL = 24, padB = 22, padT = 24, padR = 28;
      const plotW = w - padL - padR, plotH = h - padB - padT;
      ctx.strokeStyle = 'rgba(255,255,255,0.12)';
      ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(padL, padT); ctx.lineTo(padL, h - padB); ctx.lineTo(w - padR, h - padB); ctx.stroke();

      let big = '', small = '', tone: 'fly' | 'crash' | 'wait' | 'idle' = 'idle', progress = 0;
      if (r && r.status !== 'betting' && r.started_at) {
        const start = Date.parse(r.started_at);
        const crashed = r.status === 'crashed';
        const crashX = crashed ? Number(r.crash_point ?? 1) : Infinity;
        let elapsed = (t - start) / 1000;
        if (crashed) elapsed = Math.min(elapsed, Math.log(Math.max(crashX, 1)) / rate);
        const m = crashed ? crashX : multiplierAt(elapsed, rate);
        const tMax = Math.max(9, elapsed * 1.2);
        const mMax = Math.max(1.8, m * 1.25);
        const px = (s: number) => padL + (s / tMax) * plotW;
        const py = (x: number) => h - padB - ((x - 1) / (mMax - 1)) * plotH;

        // axis dots
        ctx.fillStyle = 'rgba(255,255,255,0.35)';
        for (let i = 1; i <= 7; i++) {
          ctx.beginPath(); ctx.arc(padL + (plotW * i) / 7, h - padB + 9, 1.4, 0, Math.PI * 2); ctx.fill();
        }
        ctx.fillStyle = '#34b4ff';
        for (let i = 1; i <= 5; i++) {
          ctx.beginPath(); ctx.arc(padL - 10, h - padB - (plotH * i) / 5, 1.4, 0, Math.PI * 2); ctx.fill();
        }

        if (!crashed) {
          const steps = 90;
          const trace = () => {
            ctx.beginPath();
            ctx.moveTo(px(0), py(1));
            for (let i = 1; i <= steps; i++) {
              const s = (elapsed * i) / steps;
              ctx.lineTo(px(s), py(Math.exp(rate * s)));
            }
          };
          const tipX = px(elapsed), tipY = py(Math.exp(rate * elapsed));
          trace();
          ctx.lineTo(tipX, h - padB);
          ctx.lineTo(px(0), h - padB);
          ctx.closePath();
          ctx.fillStyle = 'rgba(229,5,57,0.38)';
          ctx.fill();
          trace();
          ctx.strokeStyle = RED;
          ctx.lineWidth = 4;
          ctx.lineCap = 'round';
          ctx.stroke();

          const bob = Math.sin(t / 260) * 3;
          if (planeReady()) {
            drawPlaneImage(ctx, plane, tipX, tipY + bob, planeWidth(w, h), Math.sin(t / 700) * 0.03);
          } else {
            const back = Math.max(0, elapsed - 0.3);
            const slope = Math.atan2(py(Math.exp(rate * back)) - tipY, tipX - px(back));
            ctx.save();
            ctx.translate(tipX + 6, tipY - 10 + bob);
            ctx.rotate(-Math.max(0.06, Math.min(0.7, slope)) * 0.6);
            drawPlane(ctx, Math.max(0.9, Math.min(1.5, w / 560)), t / 18);
            ctx.restore();
          }
        } else {
          // Flew away: the plane leaves the screen, the curve is gone.
          if (crashId !== r.id) { crashId = r.id; crashSeenAt = t; }
          const away = Math.min(1, (t - crashSeenAt) / 600);
          if (away < 1) {
            const fromX = px(elapsed), fromY = py(Math.exp(rate * elapsed));
            ctx.save();
            ctx.globalAlpha = 1 - away;
            if (planeReady()) {
              drawPlaneImage(ctx, plane, fromX + away * w * 0.6, fromY - away * h * 0.6, planeWidth(w, h), -0.12 * away);
            } else {
              ctx.translate(fromX + away * w * 0.5, fromY - away * h * 0.5);
              ctx.rotate(-0.35);
              drawPlane(ctx, Math.max(0.9, Math.min(1.5, w / 560)), t / 18);
            }
            ctx.restore();
          }
        }
        big = fmtX(m);
        tone = crashed ? 'crash' : 'fly';
        small = crashed ? 'Flew away!' : '';
      } else if (r && r.status === 'betting') {
        const left = Math.max(0, Date.parse(r.betting_ends_at) - t);
        progress = Math.min(1, left / Math.max(1, bettingSeconds * 1000));
        drawPropeller(ctx, w / 2, h / 2 - 34, Math.min(46, h / 7), (t / 90) % (Math.PI * 2));
        big = 'Waiting for next round';
        small = `${(left / 1000).toFixed(1)}s`;
        tone = 'wait';
      } else {
        big = 'Connecting…';
      }

      const key = `${big}|${small}|${tone}|${progress.toFixed(2)}`;
      if (key !== lastLabel) { lastLabel = key; setLabel({ big, small, tone, progress }); }
      raf = requestAnimationFrame(frame);
    };
    raf = requestAnimationFrame(frame);
    return () => cancelAnimationFrame(raf);
  }, [now, rate, bettingSeconds]);

  return (
    <div className="relative h-[250px] overflow-hidden rounded-2xl border border-[#2c2d30] bg-[#0c0c0e] sm:h-[340px] lg:h-[420px]">
      <canvas ref={canvasRef} className="absolute inset-0 h-full w-full" aria-hidden />
      <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center text-center" aria-live="polite">
        {label.tone === 'crash' && (
          <p className="mb-1 text-xl font-extrabold uppercase tracking-wide text-white sm:text-3xl">{label.small}</p>
        )}
        {label.tone === 'wait' ? (
          <div className="mt-24 w-60 max-w-[72%]">
            <p className="mb-3 text-sm font-extrabold uppercase tracking-[0.18em] text-white">{label.big}</p>
            <div className="h-1.5 overflow-hidden rounded-full bg-[#2c2d30]">
              <div className="h-full rounded-full bg-[#e50539]" style={{ width: `${label.progress * 100}%` }} />
            </div>
          </div>
        ) : (
          <p className={`font-black tabular-nums drop-shadow-[0_6px_24px_rgba(0,0,0,0.7)] ${
            label.tone === 'idle' ? 'text-lg text-white/70' : 'text-6xl sm:text-8xl'
          } ${label.tone === 'crash' ? 'text-[#e50539]' : 'text-white'}`}>
            {label.big}
          </p>
        )}
      </div>
    </div>
  );
}
