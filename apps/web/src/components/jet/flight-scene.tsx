'use client';

import { useEffect, useRef, useState } from 'react';
import { fmtX, multiplierAt, type JetRound } from '@/lib/jet';

const LINE = '#ff3b6b';

/** A small jet, nose pointing right, drawn around (0, 0). */
function drawPlane(ctx: CanvasRenderingContext2D, scale: number) {
  ctx.save();
  ctx.scale(scale, scale);
  // fuselage
  const body = ctx.createLinearGradient(-30, -8, 30, 8);
  body.addColorStop(0, '#ff6b8b');
  body.addColorStop(1, '#e11d48');
  ctx.fillStyle = body;
  ctx.beginPath();
  ctx.moveTo(34, 0);
  ctx.quadraticCurveTo(26, -7, 6, -7);
  ctx.lineTo(-26, -5);
  ctx.quadraticCurveTo(-32, 0, -26, 5);
  ctx.lineTo(6, 7);
  ctx.quadraticCurveTo(26, 7, 34, 0);
  ctx.fill();
  // wings
  ctx.fillStyle = '#be123c';
  ctx.beginPath();
  ctx.moveTo(8, 2); ctx.lineTo(-10, 22); ctx.lineTo(-18, 22); ctx.lineTo(-6, 2); ctx.closePath(); ctx.fill();
  ctx.beginPath();
  ctx.moveTo(8, -2); ctx.lineTo(-6, -16); ctx.lineTo(-13, -16); ctx.lineTo(-6, -2); ctx.closePath(); ctx.fill();
  // tail fin
  ctx.beginPath();
  ctx.moveTo(-20, -4); ctx.lineTo(-30, -17); ctx.lineTo(-34, -17); ctx.lineTo(-29, -3); ctx.closePath(); ctx.fill();
  // cockpit
  ctx.fillStyle = '#fde68a';
  ctx.beginPath();
  ctx.ellipse(20, -2.5, 6, 2.6, -0.1, 0, Math.PI * 2);
  ctx.fill();
  // exhaust glow
  const glow = ctx.createRadialGradient(-30, 0, 0, -30, 0, 14);
  glow.addColorStop(0, 'rgba(251,191,36,0.9)');
  glow.addColorStop(1, 'rgba(251,191,36,0)');
  ctx.fillStyle = glow;
  ctx.beginPath(); ctx.arc(-32, 0, 14, 0, Math.PI * 2); ctx.fill();
  ctx.restore();
}

/**
 * The flight: a sunburst sky, the climbing curve and the plane on its tip,
 * with the live multiplier on top. Everything is derived from the server
 * clock (`now`) and the round's start time, so every player sees the same flight.
 */
export function FlightScene({ round, rate, bettingSeconds, now }: {
  round: JetRound | null; rate: number; bettingSeconds: number; now: () => number;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const roundRef = useRef(round);
  roundRef.current = round;
  const [label, setLabel] = useState<{ big: string; small: string; tone: 'fly' | 'crash' | 'wait'; progress: number }>(
    { big: '', small: '', tone: 'wait', progress: 0 },
  );

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    let raf = 0;
    let lastLabel = '';
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
      ctx.clearRect(0, 0, w, h);

      const t = now();
      // Sky with slowly turning rays.
      const bg = ctx.createRadialGradient(0, h, 0, 0, h, Math.hypot(w, h));
      bg.addColorStop(0, '#2a1145');
      bg.addColorStop(1, '#0b0716');
      ctx.fillStyle = bg;
      ctx.fillRect(0, 0, w, h);
      ctx.save();
      ctx.translate(0, h);
      ctx.rotate((t / 40000) % (Math.PI * 2));
      ctx.fillStyle = 'rgba(255,255,255,0.025)';
      for (let i = 0; i < 24; i += 2) {
        const a0 = (i / 24) * Math.PI * 2;
        const a1 = ((i + 1) / 24) * Math.PI * 2;
        ctx.beginPath();
        ctx.moveTo(0, 0);
        ctx.arc(0, 0, Math.hypot(w, h) * 1.2, a0, a1);
        ctx.closePath();
        ctx.fill();
      }
      ctx.restore();

      const padL = 34, padB = 26, padT = 20, padR = 24;
      const plotW = w - padL - padR, plotH = h - padB - padT;
      // axes
      ctx.strokeStyle = 'rgba(255,255,255,0.08)';
      ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(padL, padT); ctx.lineTo(padL, h - padB); ctx.lineTo(w - padR, h - padB); ctx.stroke();

      let big = '', small = '', tone: 'fly' | 'crash' | 'wait' = 'wait', progress = 0;
      if (r && r.status !== 'betting' && r.started_at) {
        const start = Date.parse(r.started_at);
        const crashed = r.status === 'crashed';
        const crashX = crashed ? Number(r.crash_point ?? 1) : Infinity;
        let elapsed = (t - start) / 1000;
        if (crashed) elapsed = Math.min(elapsed, Math.log(Math.max(crashX, 1)) / rate);
        const m = crashed ? crashX : multiplierAt(elapsed, rate);
        const tMax = Math.max(8, elapsed * 1.25);
        const mMax = Math.max(2, m * 1.25);
        const px = (s: number) => padL + (s / tMax) * plotW;
        const py = (x: number) => h - padB - ((x - 1) / (mMax - 1)) * plotH;

        // dots on the axes
        ctx.fillStyle = 'rgba(255,255,255,0.25)';
        for (let i = 1; i <= 6; i++) {
          ctx.beginPath(); ctx.arc(padL + (plotW * i) / 6, h - padB + 10, 1.5, 0, Math.PI * 2); ctx.fill();
          ctx.beginPath(); ctx.arc(padL - 12, h - padB - (plotH * i) / 6, 1.5, 0, Math.PI * 2); ctx.fill();
        }

        // curve + filled area
        const steps = 80;
        ctx.beginPath();
        ctx.moveTo(px(0), py(1));
        for (let i = 1; i <= steps; i++) {
          const s = (elapsed * i) / steps;
          ctx.lineTo(px(s), py(Math.exp(rate * s)));
        }
        const tipX = px(elapsed), tipY = py(Math.exp(rate * elapsed));
        ctx.save();
        const fill = ctx.createLinearGradient(0, tipY, 0, h - padB);
        fill.addColorStop(0, crashed ? 'rgba(255,59,107,0.18)' : 'rgba(255,59,107,0.42)');
        fill.addColorStop(1, 'rgba(255,59,107,0.02)');
        ctx.lineTo(tipX, h - padB);
        ctx.lineTo(px(0), h - padB);
        ctx.closePath();
        ctx.fillStyle = fill;
        ctx.fill();
        ctx.restore();
        ctx.beginPath();
        ctx.moveTo(px(0), py(1));
        for (let i = 1; i <= steps; i++) {
          const s = (elapsed * i) / steps;
          ctx.lineTo(px(s), py(Math.exp(rate * s)));
        }
        ctx.strokeStyle = LINE;
        ctx.lineWidth = 3.5;
        ctx.lineCap = 'round';
        ctx.globalAlpha = crashed ? 0.45 : 1;
        ctx.stroke();
        ctx.globalAlpha = 1;

        // plane: rides the tip, flies off when it crashes
        if (crashed && crashId !== r.id) { crashId = r.id; crashSeenAt = t; }
        const away = crashed ? Math.min(1, (t - crashSeenAt) / 700) : 0;
        if (away < 1) {
          const slope = Math.atan2(py(Math.exp(rate * Math.max(0, elapsed - 0.25))) - tipY, tipX - px(Math.max(0, elapsed - 0.25)));
          const bob = crashed ? 0 : Math.sin(t / 260) * 2.5;
          ctx.save();
          ctx.globalAlpha = 1 - away;
          ctx.translate(tipX + away * w * 0.6, tipY - away * h * 0.6 + bob);
          ctx.rotate(-Math.max(0.05, Math.min(0.9, slope)) - away * 0.5);
          drawPlane(ctx, Math.max(0.75, Math.min(1.2, w / 700)));
          ctx.restore();
        }

        big = fmtX(m);
        tone = crashed ? 'crash' : 'fly';
        small = crashed ? 'Flew away!' : '';
      } else if (r && r.status === 'betting') {
        const ends = Date.parse(r.betting_ends_at);
        const total = Math.max(1, bettingSeconds * 1000);
        const left = Math.max(0, ends - t);
        progress = Math.min(1, left / total);
        big = 'Place your bets';
        small = `Next round in ${(left / 1000).toFixed(1)}s`;
        tone = 'wait';
        // idle plane parked bottom-left
        ctx.save();
        ctx.translate(padL + 40, h - padB - 26 + Math.sin(t / 400) * 2);
        ctx.rotate(-0.08);
        drawPlane(ctx, Math.max(0.75, Math.min(1.2, w / 700)));
        ctx.restore();
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
    <div className="relative h-[260px] overflow-hidden rounded-2xl border border-white/5 bg-[#0b0716] sm:h-[340px] lg:h-[400px]">
      <canvas ref={canvasRef} className="absolute inset-0 h-full w-full" aria-hidden />
      <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center text-center" aria-live="polite">
        {label.small && label.tone === 'crash' && (
          <p className="mb-1 text-lg font-extrabold uppercase tracking-wide text-white/90 sm:text-2xl">{label.small}</p>
        )}
        <p className={`font-black tabular-nums drop-shadow-[0_4px_18px_rgba(0,0,0,0.6)] ${
          label.tone === 'wait' ? 'text-2xl text-white sm:text-3xl' : 'text-6xl sm:text-8xl'
        } ${label.tone === 'crash' ? 'text-[#ff3b6b]' : 'text-white'}`}>
          {label.big}
        </p>
        {label.tone === 'wait' && label.small && (
          <div className="mt-4 w-56 max-w-[70%]">
            <div className="h-1.5 overflow-hidden rounded-full bg-white/10">
              <div className="h-full rounded-full bg-[#ff3b6b] transition-[width] duration-100" style={{ width: `${label.progress * 100}%` }} />
            </div>
            <p className="mt-2 text-xs font-bold text-white/70">{label.small}</p>
          </div>
        )}
      </div>
    </div>
  );
}
