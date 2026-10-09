'use client';

/**
 * Game sounds, synthesised with Web Audio — no audio files to load or license.
 * Browsers only allow sound after the player interacts with the page, so the
 * audio context is created (or resumed) on the first tap/click. The on/off
 * choice is remembered per browser.
 */

const KEY = 'slyk:aviator-sound';

let ctx: AudioContext | null = null;
let master: GainNode | null = null;
let enabled = true;
let engine: { stop: () => void; set: (m: number) => void } | null = null;

try { enabled = window.localStorage.getItem(KEY) !== 'off'; } catch { /* storage blocked: default on */ }

function ac(): AudioContext | null {
  if (typeof window === 'undefined') return null;
  if (!ctx) {
    const Ctor = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!Ctor) return null;
    ctx = new Ctor();
    master = ctx.createGain();
    master.gain.value = enabled ? 1 : 0;
    master.connect(ctx.destination);
  }
  return ctx;
}

/** Call from a user gesture (the page does this on the first pointer down). */
export function unlockSound() {
  const c = ac();
  if (c && c.state === 'suspended') void c.resume();
}

export function soundEnabled() { return enabled; }

export function setSoundEnabled(on: boolean) {
  enabled = on;
  try { window.localStorage.setItem(KEY, on ? 'on' : 'off'); } catch { /* ignore */ }
  const c = ac();
  if (c && master) master.gain.setTargetAtTime(on ? 1 : 0, c.currentTime, 0.05);
  if (on) unlockSound();
}

function ready(): AudioContext | null {
  const c = ac();
  return c && c.state === 'running' && enabled ? c : null;
}

function noiseBuffer(c: AudioContext, seconds: number) {
  const buf = c.createBuffer(1, Math.ceil(c.sampleRate * seconds), c.sampleRate);
  const data = buf.getChannelData(0);
  for (let i = 0; i < data.length; i++) data[i] = Math.random() * 2 - 1;
  return buf;
}

/** A short pitched blip with a bell-like decay. */
function tone(freq: number, at: number, dur: number, vol: number, type: OscillatorType = 'sine') {
  const c = ready();
  if (!c || !master) return;
  const t = c.currentTime + at;
  const osc = c.createOscillator();
  const g = c.createGain();
  osc.type = type;
  osc.frequency.setValueAtTime(freq, t);
  g.gain.setValueAtTime(0.0001, t);
  g.gain.exponentialRampToValueAtTime(vol, t + 0.01);
  g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
  osc.connect(g).connect(master);
  osc.start(t);
  osc.stop(t + dur + 0.02);
}

/** Bet placed / cancelled: a soft click. */
export function playBet() {
  tone(880, 0, 0.08, 0.12, 'triangle');
  tone(1320, 0.04, 0.1, 0.08, 'triangle');
}

/** Cash-out: a rising coin chime. */
export function playCashout() {
  tone(1318.5, 0, 0.25, 0.18);
  tone(1760, 0.08, 0.35, 0.16);
  tone(2637, 0.16, 0.5, 0.1);
}

/** Last seconds of the countdown. */
export function playTick() {
  tone(660, 0, 0.06, 0.06, 'square');
}

/** Take-off whoosh, then the engine hum that climbs with the multiplier. */
export function startEngine() {
  const c = ready();
  if (!c || !master || engine) return;
  const t = c.currentTime;

  // Whoosh: noise swept through a rising band-pass.
  const whoosh = c.createBufferSource();
  whoosh.buffer = noiseBuffer(c, 1.2);
  const bp = c.createBiquadFilter();
  bp.type = 'bandpass'; bp.Q.value = 1.2;
  bp.frequency.setValueAtTime(300, t);
  bp.frequency.exponentialRampToValueAtTime(2400, t + 1.1);
  const wg = c.createGain();
  wg.gain.setValueAtTime(0.0001, t);
  wg.gain.exponentialRampToValueAtTime(0.22, t + 0.25);
  wg.gain.exponentialRampToValueAtTime(0.0001, t + 1.2);
  whoosh.connect(bp).connect(wg).connect(master);
  whoosh.start(t);

  // Engine: two detuned saws through a low-pass, plus a little wind noise.
  const out = c.createGain();
  out.gain.setValueAtTime(0.0001, t);
  out.gain.exponentialRampToValueAtTime(0.07, t + 0.6);
  out.connect(master);
  const lp = c.createBiquadFilter();
  lp.type = 'lowpass'; lp.frequency.value = 500; lp.Q.value = 2;
  lp.connect(out);
  const oscs = [0, 7].map((detune) => {
    const o = c.createOscillator();
    o.type = 'sawtooth'; o.frequency.value = 80; o.detune.value = detune;
    o.connect(lp); o.start(t);
    return o;
  });
  const wind = c.createBufferSource();
  wind.buffer = noiseBuffer(c, 2); wind.loop = true;
  const wf = c.createBiquadFilter();
  wf.type = 'highpass'; wf.frequency.value = 1500;
  const wgain = c.createGain(); wgain.gain.value = 0.25;
  wind.connect(wf).connect(wgain).connect(out);
  wind.start(t);

  engine = {
    set(m: number) {
      const now = c.currentTime;
      const lift = Math.log(Math.max(1, m)); // 0 at 1x, ~2.3 at 10x
      const f = 80 + Math.min(lift, 4) * 45;
      oscs.forEach((o) => o.frequency.setTargetAtTime(f, now, 0.2));
      lp.frequency.setTargetAtTime(500 + Math.min(lift, 4) * 450, now, 0.2);
    },
    stop() {
      const now = c.currentTime;
      out.gain.cancelScheduledValues(now);
      out.gain.setTargetAtTime(0.0001, now, 0.08);
      oscs.forEach((o) => o.stop(now + 0.5));
      wind.stop(now + 0.5);
    },
  };
}

export function updateEngine(multiplier: number) { engine?.set(multiplier); }

export function stopEngine() {
  engine?.stop();
  engine = null;
}

/** Flew away: the engine cuts and the plane zooms off with a falling whoosh. */
export function playCrash() {
  stopEngine();
  const c = ready();
  if (!c || !master) return;
  const t = c.currentTime;
  const src = c.createBufferSource();
  src.buffer = noiseBuffer(c, 1);
  const bp = c.createBiquadFilter();
  bp.type = 'bandpass'; bp.Q.value = 2;
  bp.frequency.setValueAtTime(2600, t);
  bp.frequency.exponentialRampToValueAtTime(200, t + 0.9);
  const g = c.createGain();
  g.gain.setValueAtTime(0.3, t);
  g.gain.exponentialRampToValueAtTime(0.0001, t + 0.95);
  src.connect(bp).connect(g).connect(master);
  src.start(t);

  const o = c.createOscillator();
  o.type = 'triangle';
  o.frequency.setValueAtTime(520, t);
  o.frequency.exponentialRampToValueAtTime(90, t + 0.7);
  const og = c.createGain();
  og.gain.setValueAtTime(0.12, t);
  og.gain.exponentialRampToValueAtTime(0.0001, t + 0.75);
  o.connect(og).connect(master);
  o.start(t); o.stop(t + 0.8);
}
