'use client';

/**
 * Game sounds and background music, synthesised with Web Audio — no audio
 * files to load or license. Browsers only allow sound after the player
 * interacts with the page, so the audio context is created (or resumed) on
 * the first tap/click. Sound and music each have their own on/off switch,
 * remembered per browser.
 */

const KEY = 'slyk:aviator-sound';
const MUSIC_KEY = 'slyk:aviator-music';

let ctx: AudioContext | null = null;
let master: GainNode | null = null; // sound effects
let musicBus: GainNode | null = null;
let enabled = true;
let musicOn = true;
let engine: { stop: () => void; set: (m: number) => void } | null = null;

try {
  enabled = window.localStorage.getItem(KEY) !== 'off';
  musicOn = window.localStorage.getItem(MUSIC_KEY) !== 'off';
} catch { /* storage blocked (or rendering on the server): defaults on */ }

function ac(): AudioContext | null {
  if (typeof window === 'undefined') return null;
  if (!ctx) {
    const Ctor = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!Ctor) return null;
    ctx = new Ctor();
    master = ctx.createGain();
    master.gain.value = enabled ? 1 : 0;
    master.connect(ctx.destination);
    musicBus = ctx.createGain();
    musicBus.gain.value = musicOn ? MUSIC_VOLUME : 0;
    musicBus.connect(ctx.destination);
  }
  return ctx;
}

/** Call from a user gesture (the page does this on the first pointer down). */
export function unlockSound() {
  const c = ac();
  if (!c) return;
  if (c.state === 'suspended') void c.resume().then(() => { if (musicOn) startMusic(); });
  else if (musicOn) startMusic();
}

export function musicEnabled() { return musicOn; }

export function setMusicEnabled(on: boolean) {
  musicOn = on;
  try { window.localStorage.setItem(MUSIC_KEY, on ? 'on' : 'off'); } catch { /* ignore */ }
  const c = ac();
  if (c && musicBus) musicBus.gain.setTargetAtTime(on ? MUSIC_VOLUME : 0, c.currentTime, 0.3);
  if (on) unlockSound();
  else window.setTimeout(() => { if (!musicOn) stopMusic(); }, 1200);
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

let noiseCache: AudioBuffer | null = null;
function noiseBuffer(c: AudioContext, seconds: number) {
  if (noiseCache && noiseCache.duration >= seconds) return noiseCache;
  const buf = c.createBuffer(1, Math.ceil(c.sampleRate * seconds), c.sampleRate);
  const data = buf.getChannelData(0);
  for (let i = 0; i < data.length; i++) data[i] = Math.random() * 2 - 1;
  noiseCache = buf;
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

/* ------------------------------------------------------------------------ */
/* Background music: a laid-back synth loop (pad, arpeggio, bass, soft beat) */
/* scheduled a little ahead of time so it stays in time.                    */
/* ------------------------------------------------------------------------ */

const MUSIC_VOLUME = 0.55;
const BPM = 100;
const STEP = 60 / BPM / 2; // eighth notes
// Am9 – Fmaj7 – Cadd9 – G6, as MIDI notes.
const CHORDS = [
  [57, 60, 64, 67, 71],
  [53, 57, 60, 64, 67],
  [48, 52, 55, 59, 62],
  [55, 59, 62, 64, 67],
];
const ARP = [0, 2, 4, 2, 1, 3, 4, 3];
const midi = (n: number) => 440 * 2 ** ((n - 69) / 12);

let music: { timer: number; next: number; step: number; filter: BiquadFilterNode } | null = null;
let energy = 0; // 0 waiting, 1 flying — opens the filter and adds drive

/** Lift the music while the plane is in the air (0–1). */
export function setMusicEnergy(v: number) {
  energy = Math.max(0, Math.min(1, v));
  if (music && ctx) music.filter.frequency.setTargetAtTime(1400 + energy * 2600, ctx.currentTime, 0.6);
}

function note(c: AudioContext, out: AudioNode, freq: number, at: number, dur: number, vol: number,
  type: OscillatorType, attack = 0.01, detune = 0) {
  const o = c.createOscillator();
  const g = c.createGain();
  o.type = type; o.frequency.value = freq; o.detune.value = detune;
  g.gain.setValueAtTime(0.0001, at);
  g.gain.linearRampToValueAtTime(vol, at + attack);
  g.gain.exponentialRampToValueAtTime(0.0001, at + dur);
  o.connect(g).connect(out);
  o.start(at); o.stop(at + dur + 0.05);
}

function scheduleStep(c: AudioContext, out: AudioNode, step: number, at: number) {
  const bar = Math.floor(step / 8) % CHORDS.length;
  const beat = step % 8;
  const chord = CHORDS[bar];

  // Pad: the chord, held for the bar, softly detuned.
  if (beat === 0) {
    for (const n of chord.slice(0, 4)) {
      note(c, out, midi(n), at, STEP * 8.6, 0.022, 'sawtooth', 0.5, -6);
      note(c, out, midi(n), at, STEP * 8.6, 0.022, 'sawtooth', 0.5, 6);
    }
  }
  // Arpeggio an octave up.
  note(c, out, midi(chord[ARP[beat]] + 12), at, STEP * 1.8, 0.05 + energy * 0.02, 'triangle');
  // Bass on beats 1 and 3, a push before the bar line.
  if (beat === 0 || beat === 4 || beat === 7) note(c, out, midi(chord[0] - 24), at, STEP * (beat === 7 ? 0.9 : 2.5), 0.16, 'sine', 0.02);
  // Soft kick and hats.
  if (beat === 0 || beat === 4) {
    const o = c.createOscillator();
    const g = c.createGain();
    o.frequency.setValueAtTime(130, at);
    o.frequency.exponentialRampToValueAtTime(42, at + 0.18);
    g.gain.setValueAtTime(0.22, at);
    g.gain.exponentialRampToValueAtTime(0.0001, at + 0.25);
    o.connect(g).connect(out);
    o.start(at); o.stop(at + 0.3);
  }
  if (beat % 2 === 1 || energy > 0.5) {
    const src = c.createBufferSource();
    src.buffer = noiseBuffer(c, 2);
    const hp = c.createBiquadFilter();
    hp.type = 'highpass'; hp.frequency.value = 7000;
    const g = c.createGain();
    g.gain.setValueAtTime(beat % 2 === 1 ? 0.035 : 0.018, at);
    g.gain.exponentialRampToValueAtTime(0.0001, at + 0.05);
    src.connect(hp).connect(g).connect(out);
    src.start(at, Math.random() * 1.5, 0.06);
  }
}

export function startMusic() {
  const c = ac();
  if (!c || !musicBus || music || c.state !== 'running') return;
  const filter = c.createBiquadFilter();
  filter.type = 'lowpass'; filter.frequency.value = 1400 + energy * 2600; filter.Q.value = 0.7;
  filter.connect(musicBus);
  const m = { timer: 0, next: c.currentTime + 0.1, step: 0, filter };
  m.timer = window.setInterval(() => {
    while (m.next < c.currentTime + 0.2) {
      scheduleStep(c, filter, m.step, m.next);
      m.next += STEP;
      m.step = (m.step + 1) % (8 * CHORDS.length);
    }
  }, 50);
  music = m;
}

export function stopMusic() {
  if (!music) return;
  window.clearInterval(music.timer);
  const f = music.filter;
  window.setTimeout(() => f.disconnect(), 3000);
  music = null;
}
