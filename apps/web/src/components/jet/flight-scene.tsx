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

/** Multiplier colour bands, as in the history strip: blue, purple, pink. */
function bandColor(m: number): [number, number, number] {
  if (m >= 10) return [192, 23, 180];
  if (m >= 2) return [145, 62, 248];
  return [52, 180, 255];
}

interface Star { x: number; y: number; r: number; tw: number; depth: number }
interface Puff { x: number; y: number; vx: number; vy: number; born: number; size: number }

/**
 * The flight, Aviator-style: a dark sky with a turning sunburst and a glow that
 * changes colour with the multiplier, drifting stars for speed, the glowing
 * red curve with the plane (and its exhaust trail) on the tip, the multiplier
 * on top, and a red flash when it flies away. Everything comes from the server
 * clock (`now`) and the round's start time, so every player sees the same flight.
 */
export function FlightScene({ round, rate, bettingSeconds, now, name }: {
  round: JetRound | null; rate: number; bettingSeconds: number; now: () => number; name?: string;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const roundRef = useRef(round);
  roundRef.current = round;
  const [label, setLabel] = useState<{ big: string; small: string; tone: 'fly' | 'crash' | 'wait' | 'idle'; progress: number; band: number }>(
    { big: '', small: '', tone: 'idle', progress: 0, band: 0 },
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
    let lastT = 0;
    let rayAngle = 0;
    let glow: [number, number, number] = [52, 180, 255];
    const stars: Star[] = Array.from({ length: 70 }, () => ({
      x: Math.random(), y: Math.random(), r: Math.random() * 1.3 + 0.3, tw: Math.random() * Math.PI * 2, depth: Math.random() * 0.8 + 0.2,
    }));
    let puffs: Puff[] = [];

    const frame = () => {
      const r = roundRef.current;
      const dpr = Math.min(2, window.devicePixelRatio || 1);
      const w = canvas.clientWidth;
      const h = canvas.clientHeight;
      if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) {
        canvas.width = Math.round(w * dpr);
        canvas.height = Math.round(h * dpr);
      }
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      const t = now();
      const dt = lastT ? Math.min(0.1, (t - lastT) / 1000) : 0;
      lastT = t;
      const flying = r?.status === 'flying';
      const crashed = r?.status === 'crashed';

      // Live multiplier (for colours and speed) before drawing the sky.
      let m = 1;
      let elapsed = 0;
      if (r && r.status !== 'betting' && r.started_at) {
        elapsed = (t - Date.parse(r.started_at)) / 1000;
        if (crashed) {
          m = Number(r.crash_point ?? 1);
          elapsed = Math.min(elapsed, Math.log(Math.max(m, 1)) / rate);
        } else m = multiplierAt(elapsed, rate);
      }
      const speed = flying ? Math.min(3, 0.6 + Math.log(m) * 1.2) : crashed ? 0.15 : 0.08;

      // Sky.
      const bg = ctx.createLinearGradient(0, 0, 0, h);
      bg.addColorStop(0, '#0b0b10');
      bg.addColorStop(1, '#050507');
      ctx.fillStyle = bg;
      ctx.fillRect(0, 0, w, h);

      // Glow, easing toward the multiplier's colour band.
      const target = crashed ? [229, 5, 57] as [number, number, number] : flying ? bandColor(m) : [229, 5, 57] as [number, number, number];
      glow = glow.map((c, i) => c + (target[i] - c) * Math.min(1, dt * 2.5)) as [number, number, number];
      const gx = flying ? w * 0.62 : w / 2, gy = flying ? h * 0.42 : h / 2;
      const rg = ctx.createRadialGradient(gx, gy, 0, gx, gy, Math.max(w, h) * 0.75);
      rg.addColorStop(0, `rgba(${glow.map(Math.round).join(',')},${flying ? 0.28 : 0.14})`);
      rg.addColorStop(1, 'rgba(0,0,0,0)');
      ctx.fillStyle = rg;
      ctx.fillRect(0, 0, w, h);

      // Sunburst turning around the bottom-left corner — faster in flight.
      rayAngle = (rayAngle + dt * (flying ? 0.09 : 0.02)) % (Math.PI * 2);
      ctx.save();
      ctx.translate(0, h);
      ctx.rotate(rayAngle);
      const reach = Math.hypot(w, h) * 1.4;
      const rays = ctx.createRadialGradient(0, 0, 0, 0, 0, reach);
      rays.addColorStop(0, 'rgba(255,255,255,0.075)');
      rays.addColorStop(0.6, 'rgba(255,255,255,0.03)');
      rays.addColorStop(1, 'rgba(255,255,255,0.01)');
      ctx.fillStyle = rays;
      ctx.beginPath();
      for (let i = 0; i < 40; i += 2) {
        const a0 = (i / 40) * Math.PI * 2, a1 = ((i + 1) / 40) * Math.PI * 2;
        ctx.moveTo(0, 0); ctx.arc(0, 0, reach, a0, a1); ctx.closePath();
      }
      ctx.fill();
      ctx.restore();

      // Stars drifting left and down: the faster the climb, the faster they pass.
      for (const st of stars) {
        st.x -= dt * speed * 0.06 * st.depth;
        st.y += dt * speed * 0.025 * st.depth;
        if (st.x < 0) st.x += 1;
        if (st.y > 1) st.y -= 1;
        const a = (0.35 + 0.45 * Math.sin(t / 600 + st.tw)) * st.depth;
        ctx.fillStyle = `rgba(255,255,255,${a.toFixed(3)})`;
        ctx.beginPath(); ctx.arc(st.x * w, st.y * h, st.r, 0, Math.PI * 2); ctx.fill();
      }

      const padL = 28, padB = 26, padT = 24, padR = 28;
      const plotW = w - padL - padR, plotH = h - padB - padT;
      ctx.strokeStyle = 'rgba(255,255,255,0.14)';
      ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(padL, padT); ctx.lineTo(padL, h - padB); ctx.lineTo(w - padR, h - padB); ctx.stroke();

      let big = '', small = '', tone: 'fly' | 'crash' | 'wait' | 'idle' = 'idle', progress = 0;
      if (r && r.status !== 'betting' && r.started_at) {
        const tMax = Math.max(9, elapsed * 1.2);
        const mMax = Math.max(1.8, m * 1.25);
        const px = (s: number) => padL + (s / tMax) * plotW;
        const py = (x: number) => h - padB - ((x - 1) / (mMax - 1)) * plotH;

        // Axis dots that slide as the scale grows: one per second / per step.
        ctx.fillStyle = 'rgba(255,255,255,0.4)';
        const secStep = Math.max(1, Math.ceil(tMax / 9));
        for (let s = secStep; s < tMax; s += secStep) {
          ctx.beginPath(); ctx.arc(px(s), h - padB + 11, 1.5, 0, Math.PI * 2); ctx.fill();
        }
        ctx.fillStyle = '#34b4ff';
        const mStep = mMax > 20 ? 10 : mMax > 6 ? 2 : mMax > 3 ? 0.5 : 0.2;
        for (let x = 1 + mStep; x < mMax; x += mStep) {
          ctx.beginPath(); ctx.arc(padL - 12, py(x), 1.5, 0, Math.PI * 2); ctx.fill();
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
          const fill = ctx.createLinearGradient(0, tipY, 0, h - padB);
          fill.addColorStop(0, 'rgba(229,5,57,0.55)');
          fill.addColorStop(1, 'rgba(229,5,57,0.12)');
          ctx.fillStyle = fill;
          ctx.fill();
          trace();
          ctx.save();
          ctx.shadowColor = 'rgba(255,30,80,0.9)';
          ctx.shadowBlur = 14;
          ctx.strokeStyle = RED;
          ctx.lineWidth = 4;
          ctx.lineCap = 'round';
          ctx.stroke();
          ctx.restore();

          // Exhaust puffs from the tail.
          if (flying && dt > 0) {
            puffs.push({ x: tipX, y: tipY, vx: -40 - Math.random() * 30, vy: 10 + Math.random() * 20, born: t, size: 3 + Math.random() * 3 });
          }
          puffs = puffs.filter((p) => t - p.born < 700);
          for (const p of puffs) {
            const age = (t - p.born) / 700;
            p.x += p.vx * dt; p.y += p.vy * dt;
            ctx.fillStyle = `rgba(255,255,255,${(0.22 * (1 - age)).toFixed(3)})`;
            ctx.beginPath(); ctx.arc(p.x, p.y, p.size * (1 + age * 2), 0, Math.PI * 2); ctx.fill();
          }

          // Glow on the tip.
          const tg = ctx.createRadialGradient(tipX, tipY, 0, tipX, tipY, 26);
          tg.addColorStop(0, 'rgba(255,90,120,0.9)');
          tg.addColorStop(1, 'rgba(255,90,120,0)');
          ctx.fillStyle = tg;
          ctx.beginPath(); ctx.arc(tipX, tipY, 26, 0, Math.PI * 2); ctx.fill();

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
          // Flew away: a red flash, and the plane leaves the screen.
          if (crashId !== r.id) { crashId = r.id; crashSeenAt = t; puffs = []; }
          const since = t - crashSeenAt;
          const flash = Math.max(0, 1 - since / 700);
          if (flash > 0) {
            const fg = ctx.createRadialGradient(w / 2, h / 2, 0, w / 2, h / 2, Math.max(w, h) * 0.7);
            fg.addColorStop(0, `rgba(229,5,57,${(0.35 * flash).toFixed(3)})`);
            fg.addColorStop(1, `rgba(229,5,57,${(0.12 * flash).toFixed(3)})`);
            ctx.fillStyle = fg;
            ctx.fillRect(0, 0, w, h);
          }
          const away = Math.min(1, since / 600);
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
        const pr = Math.min(46, h / 7.5);
        const cx = w / 2, cy = h / 2 - pr - 34;
        // Spinning blur disc behind the propeller.
        const disc = ctx.createRadialGradient(cx, cy, pr * 0.2, cx, cy, pr * 1.15);
        disc.addColorStop(0, 'rgba(229,5,57,0.25)');
        disc.addColorStop(1, 'rgba(229,5,57,0)');
        ctx.fillStyle = disc;
        ctx.beginPath(); ctx.arc(cx, cy, pr * 1.15, 0, Math.PI * 2); ctx.fill();
        drawPropeller(ctx, cx, cy, pr, (t / 70) % (Math.PI * 2));
        big = 'Waiting for next round';
        small = `${(left / 1000).toFixed(1)}s`;
        tone = 'wait';
      } else {
        big = 'Connecting…';
      }

      const band = m >= 10 ? 2 : m >= 2 ? 1 : 0;
      const key = `${big}|${small}|${tone}|${progress.toFixed(3)}|${band}`;
      if (key !== lastLabel) { lastLabel = key; setLabel({ big, small, tone, progress, band }); }
      raf = requestAnimationFrame(frame);
    };
    raf = requestAnimationFrame(frame);
    return () => cancelAnimationFrame(raf);
  }, [now, rate, bettingSeconds]);

  const [brand, ...rest] = (name ?? '').split(' ');
  const glowText = ['rgba(52,180,255,0.55)', 'rgba(145,62,248,0.6)', 'rgba(192,23,180,0.65)'][label.band];

  return (
    <div className="relative h-[260px] overflow-hidden rounded-2xl border border-[#2c2d30] bg-[#07070a] shadow-[inset_0_0_60px_rgba(0,0,0,0.8)] sm:h-[340px] lg:h-[420px]">
      <canvas ref={canvasRef} className="absolute inset-0 h-full w-full" aria-hidden />
      <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center text-center" aria-live="polite">
        {label.tone === 'crash' && (
          <p className="mb-1 animate-[jet-pop_0.35s_ease-out] text-xl font-extrabold uppercase tracking-[0.12em] text-white sm:text-3xl">{label.small}</p>
        )}
        {label.tone === 'wait' ? (
          <div className="mt-28 w-64 max-w-[76%]">
            {name && (
              <p className="mb-2 leading-none">
                {rest.length > 0 && <span className="block text-[10px] font-extrabold uppercase tracking-[0.25em] text-white/70">{brand}</span>}
                <span className="text-3xl font-black italic text-[#e50539] [text-shadow:0_2px_14px_rgba(229,5,57,0.5)]">{rest.length ? rest.join(' ') : brand}</span>
              </p>
            )}
            <p className="mb-3 text-xs font-extrabold uppercase tracking-[0.2em] text-white/90">{label.big}</p>
            <div className="h-2 overflow-hidden rounded-full bg-white/10">
              <div className="h-full rounded-full bg-gradient-to-r from-[#ff2b5e] to-[#e50539] shadow-[0_0_12px_rgba(229,5,57,0.8)]" style={{ width: `${label.progress * 100}%` }} />
            </div>
            <p className="mt-2 text-xs font-bold tabular-nums text-white/60">{label.small}</p>
          </div>
        ) : (
          <p
            className={`font-black tabular-nums ${label.tone === 'idle' ? 'text-lg text-white/70' : 'text-6xl sm:text-8xl'} ${label.tone === 'crash' ? 'text-[#e50539]' : 'text-white'}`}
            style={label.tone === 'fly' ? { textShadow: `0 0 28px ${glowText}, 0 6px 24px rgba(0,0,0,0.7)` }
              : label.tone === 'crash' ? { textShadow: '0 0 30px rgba(229,5,57,0.6)' } : undefined}
          >
            {label.big}
          </p>
        )}
      </div>
    </div>
  );
}
