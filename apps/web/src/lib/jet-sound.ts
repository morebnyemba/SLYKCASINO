'use client';

/**
 * Game sounds and background music. By default everything is synthesised
 * with Web Audio (nothing to load or license). Licensed audio files can be
 * dropped into public/aviator/sounds/ and are used instead when present:
 *   music.mp3 (looped) · flying.mp3 (looped in flight) · takeoff.mp3
 *   flew-away.mp3 · cashout.mp3 · bet.mp3
 * Browsers only allow sound after the player interacts with the page, so the
 * audio context is created (or resumed) on the first tap/click. Sound and
 * music each have their own on/off switch, remembered per browser.
 */

const KEY = 'slyk:aviator-sound';
const MUSIC_KEY = 'slyk:aviator-music';

let ctx: AudioContext | null = null;
let master: GainNode | null = null; // sound effects
let musicBus: GainNode | null = null;
let enabled = true;
let musicOn = true;
let engine: { stop: () => void; set: (m: number) => void } | null = null;

const CLIP_FILES = {
  music: 'music', flying: 'flying', takeoff: 'takeoff', crash: 'flew-away', cashout: 'cashout', bet: 'bet',
} as const;
type Clip = keyof typeof CLIP_FILES;
const clips: Partial<Record<Clip, AudioBuffer | null>> = {};
let clipsRequested = false;

/** Fetch any audio files the site provides; missing ones fall back to the synth. */
function loadClips(c: AudioContext) {
  if (clipsRequested) return;
  clipsRequested = true;
  void fetch('/aviator/sounds')
    .then((r) => (r.ok ? r.json() : { files: [] }))
    .then(({ files }: { files: string[] }) => {
      for (const [key, file] of Object.entries(CLIP_FILES) as [Clip, string][]) {
        if (files.includes(`${file}.mp3`)) loadClip(c, key, file);
      }
    })
    .catch(() => { /* no files: synth only */ });
}

function loadClip(c: AudioContext, key: Clip, file: string) {
  fetch(`/aviator/sounds/${file}.mp3`)
    .then((r) => (r.ok ? r.arrayBuffer() : null))
    .then((data) => (data ? c.decodeAudioData(data) : null))
    .then((buf) => {
      clips[key] = buf;
      // The music file arrived after the synth loop started: swap over.
      if (key === 'music' && buf && music?.kind === 'synth') { stopMusic(); startMusic(); }
    })
    .catch(() => { clips[key] = null; });
}

function playClip(key: Clip, opts: { loop?: boolean; volume?: number; out?: AudioNode } = {}) {
  const c = ctx;
  const buf = clips[key];
  if (!c || !buf || !master) return null;
  const src = c.createBufferSource();
  src.buffer = buf;
  src.loop = !!opts.loop;
  const g = c.createGain();
  g.gain.value = opts.volume ?? 1;
  src.connect(g).connect(opts.out ?? master);
  src.start();
  return { src, gain: g };
}

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
  loadClips(c);
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

/** Bet placed / cancelled: a short wooden click. */
export function playBet() {
  if (!ready()) return;
  if (clips.bet) { playClip('bet'); return; }
  tone(1200, 0, 0.05, 0.14, 'square');
  tone(1800, 0.025, 0.06, 0.08, 'triangle');
}

/** Cash-out: a bright "cha-ching" with a little shimmer. */
export function playCashout() {
  if (!ready()) return;
  if (clips.cashout) { playClip('cashout'); return; }
  tone(1567.98, 0, 0.12, 0.16, 'square');
  tone(2093, 0.07, 0.4, 0.16, 'square');
  tone(3136, 0.07, 0.6, 0.07);
  tone(4186, 0.12, 0.7, 0.05);
}

/** Last seconds of the countdown. */
export function playTick() {
  tone(980, 0, 0.04, 0.05, 'triangle');
}

/**
 * Take-off, then the propeller drone: a low buzz chopped by the propeller
 * that revs up as the multiplier climbs.
 */
export function startEngine() {
  const c = ready();
  if (!c || !master || engine) return;
  const t = c.currentTime;

  if (clips.takeoff) playClip('takeoff');
  const file = clips.flying ? playClip('flying', { loop: true, volume: 0.0001 }) : null;
  if (file) {
    file.gain.gain.exponentialRampToValueAtTime(0.9, t + 0.8);
    engine = {
      set(m: number) { file.src.playbackRate.setTargetAtTime(1 + Math.min(Math.log(Math.max(1, m)), 3) * 0.08, c.currentTime, 0.3); },
      stop() { const now = c.currentTime; file.gain.gain.setTargetAtTime(0.0001, now, 0.06); file.src.stop(now + 0.4); },
    };
    return;
  }

  if (!clips.takeoff) {
    // Rev-up: the drone's pitch swings up from idle.
    const rev = c.createOscillator();
    const rg = c.createGain();
    rev.type = 'sawtooth';
    rev.frequency.setValueAtTime(40, t);
    rev.frequency.exponentialRampToValueAtTime(95, t + 0.9);
    rg.gain.setValueAtTime(0.0001, t);
    rg.gain.exponentialRampToValueAtTime(0.06, t + 0.2);
    rg.gain.exponentialRampToValueAtTime(0.0001, t + 1);
    const rlp = c.createBiquadFilter();
    rlp.type = 'lowpass'; rlp.frequency.value = 900;
    rev.connect(rlp).connect(rg).connect(master);
    rev.start(t); rev.stop(t + 1.05);
  }

  // Drone: saw + square an octave apart, through a low-pass, amplitude-chopped
  // by a fast LFO (the propeller), with a little air noise on top.
  const out = c.createGain();
  out.gain.setValueAtTime(0.0001, t);
  out.gain.exponentialRampToValueAtTime(0.085, t + 0.7);
  out.connect(master);
  const chop = c.createGain();
  chop.gain.value = 0.7;
  const lfo = c.createOscillator();
  lfo.frequency.value = 24;
  const lfoDepth = c.createGain();
  lfoDepth.gain.value = 0.3;
  lfo.connect(lfoDepth).connect(chop.gain);
  chop.connect(out);
  const lp = c.createBiquadFilter();
  lp.type = 'lowpass'; lp.frequency.value = 650; lp.Q.value = 3;
  lp.connect(chop);
  const saw = c.createOscillator();
  saw.type = 'sawtooth'; saw.frequency.value = 95;
  const sq = c.createOscillator();
  sq.type = 'square'; sq.frequency.value = 47.5;
  const sqg = c.createGain(); sqg.gain.value = 0.5;
  saw.connect(lp); sq.connect(sqg).connect(lp);
  const air = c.createBufferSource();
  air.buffer = noiseBuffer(c, 2); air.loop = true;
  const af = c.createBiquadFilter();
  af.type = 'bandpass'; af.frequency.value = 1800; af.Q.value = 0.6;
  const ag = c.createGain(); ag.gain.value = 0.18;
  air.connect(af).connect(ag).connect(out);
  [lfo, saw, sq, air].forEach((n) => n.start(t));

  engine = {
    set(m: number) {
      const now = c.currentTime;
      const lift = Math.min(Math.log(Math.max(1, m)), 4); // 0 at 1x, ~2.3 at 10x
      saw.frequency.setTargetAtTime(95 + lift * 38, now, 0.25);
      sq.frequency.setTargetAtTime((95 + lift * 38) / 2, now, 0.25);
      lfo.frequency.setTargetAtTime(24 + lift * 9, now, 0.25);
      lp.frequency.setTargetAtTime(650 + lift * 420, now, 0.25);
    },
    stop() {
      const now = c.currentTime;
      out.gain.cancelScheduledValues(now);
      out.gain.setTargetAtTime(0.0001, now, 0.06);
      [lfo, saw, sq, air].forEach((n) => n.stop(now + 0.4));
    },
  };
}

export function updateEngine(multiplier: number) { engine?.set(multiplier); }

export function stopEngine() {
  engine?.stop();
  engine = null;
}

/** Flew away: the plane zooms past and away — a buzz that drops in pitch (Doppler) under a whoosh. */
export function playCrash() {
  stopEngine();
  const c = ready();
  if (!c || !master) return;
  if (clips.crash) { playClip('crash'); return; }
  const t = c.currentTime;

  const o = c.createOscillator();
  o.type = 'sawtooth';
  o.frequency.setValueAtTime(260, t);
  o.frequency.exponentialRampToValueAtTime(70, t + 0.9);
  const lp = c.createBiquadFilter();
  lp.type = 'lowpass';
  lp.frequency.setValueAtTime(2200, t);
  lp.frequency.exponentialRampToValueAtTime(300, t + 0.9);
  const og = c.createGain();
  og.gain.setValueAtTime(0.0001, t);
  og.gain.exponentialRampToValueAtTime(0.14, t + 0.06);
  og.gain.exponentialRampToValueAtTime(0.0001, t + 1);
  o.connect(lp).connect(og).connect(master);
  o.start(t); o.stop(t + 1.05);

  const src = c.createBufferSource();
  src.buffer = noiseBuffer(c, 2);
  const bp = c.createBiquadFilter();
  bp.type = 'bandpass'; bp.Q.value = 1.5;
  bp.frequency.setValueAtTime(3000, t);
  bp.frequency.exponentialRampToValueAtTime(400, t + 0.8);
  const g = c.createGain();
  g.gain.setValueAtTime(0.0001, t);
  g.gain.exponentialRampToValueAtTime(0.26, t + 0.05);
  g.gain.exponentialRampToValueAtTime(0.0001, t + 0.85);
  src.connect(bp).connect(g).connect(master);
  src.start(t, 0, 0.9);
}

/* ------------------------------------------------------------------------ */
/* Background music: a laid-back synth loop (pad, arpeggio, bass, soft beat) */
/* scheduled a little ahead of time so it stays in time.                    */
/* ------------------------------------------------------------------------ */

const MUSIC_VOLUME = 0.5;
const BPM = 118;
const STEP = 60 / BPM / 2; // eighth notes
// I–V–vi–IV in C: bouncy and bright, like an arcade game's lobby loop.
const ROOTS = [48, 43, 45, 41];
const STABS = [[60, 64, 67], [59, 62, 67], [60, 64, 69], [60, 65, 69]];
const LEAD: (number | null)[][] = [
  [72, null, 76, 79, 76, null, 74, 72],
  [71, null, 74, 79, 74, null, 71, 67],
  [69, null, 72, 76, 72, null, 74, 76],
  [77, 76, 74, 72, 69, null, 72, null],
];
const midi = (n: number) => 440 * 2 ** ((n - 69) / 12);

let music:
  | { kind: 'synth'; timer: number; next: number; step: number; filter: BiquadFilterNode }
  | { kind: 'file'; src: AudioBufferSourceNode; filter: BiquadFilterNode }
  | null = null;
let energy = 0; // 0 waiting, 1 flying — opens the filter and adds drive

/** Lift the music while the plane is in the air (0–1). */
export function setMusicEnergy(v: number) {
  energy = Math.max(0, Math.min(1, v));
  if (music?.kind === 'synth' && ctx) music.filter.frequency.setTargetAtTime(2200 + energy * 3800, ctx.currentTime, 0.6);
}

function note(c: AudioContext, out: AudioNode, freq: number, at: number, dur: number, vol: number,
  type: OscillatorType, attack = 0.005, detune = 0) {
  const o = c.createOscillator();
  const g = c.createGain();
  o.type = type; o.frequency.value = freq; o.detune.value = detune;
  g.gain.setValueAtTime(0.0001, at);
  g.gain.linearRampToValueAtTime(vol, at + attack);
  g.gain.exponentialRampToValueAtTime(0.0001, at + dur);
  o.connect(g).connect(out);
  o.start(at); o.stop(at + dur + 0.05);
}

function hit(c: AudioContext, out: AudioNode, at: number, freq: number, q: number, vol: number, dur: number, type: BiquadFilterType = 'bandpass') {
  const src = c.createBufferSource();
  src.buffer = noiseBuffer(c, 2);
  const f = c.createBiquadFilter();
  f.type = type; f.frequency.value = freq; f.Q.value = q;
  const g = c.createGain();
  g.gain.setValueAtTime(vol, at);
  g.gain.exponentialRampToValueAtTime(0.0001, at + dur);
  src.connect(f).connect(g).connect(out);
  src.start(at, Math.random() * 1.5, dur + 0.02);
}

function scheduleStep(c: AudioContext, out: AudioNode, step: number, at: number) {
  const bar = Math.floor(step / 8) % ROOTS.length;
  const beat = step % 8;
  const root = ROOTS[bar];

  // Bouncy bass: root on the beat, octave on the "and".
  note(c, out, midi(beat % 2 === 0 ? root : root + 12), at, STEP * 0.9, 0.17, 'triangle');
  // Off-beat chord stabs.
  if (beat % 2 === 1) for (const n of STABS[bar]) note(c, out, midi(n), at, STEP * 0.7, 0.03, 'sawtooth', 0.005, beat === 3 ? 4 : -4);
  // Plucky lead melody (comes in fuller while flying).
  const lead = LEAD[bar][beat];
  if (lead !== null) note(c, out, midi(lead), at, STEP * 1.1, 0.045 + energy * 0.02, 'square');
  // Kick on 1 and 3, clap on 2 and 4, hats on every off-beat.
  if (beat === 0 || beat === 4) {
    const o = c.createOscillator();
    const g = c.createGain();
    o.frequency.setValueAtTime(150, at);
    o.frequency.exponentialRampToValueAtTime(45, at + 0.15);
    g.gain.setValueAtTime(0.3, at);
    g.gain.exponentialRampToValueAtTime(0.0001, at + 0.22);
    o.connect(g).connect(out);
    o.start(at); o.stop(at + 0.25);
  }
  if (beat === 2 || beat === 6) hit(c, out, at, 1400, 0.9, 0.13, 0.14);
  if (beat % 2 === 1) hit(c, out, at, 8000, 0.7, 0.05, 0.04, 'highpass');
  else if (energy > 0.5) hit(c, out, at, 8000, 0.7, 0.025, 0.03, 'highpass');
}

export function startMusic() {
  const c = ac();
  if (!c || !musicBus || music || c.state !== 'running') return;
  const filter = c.createBiquadFilter();
  filter.type = 'lowpass'; filter.Q.value = 0.7;
  filter.connect(musicBus);
  if (clips.music) {
    filter.frequency.value = 20000;
    const src = c.createBufferSource();
    src.buffer = clips.music; src.loop = true;
    src.connect(filter);
    src.start();
    music = { kind: 'file', src, filter };
    return;
  }
  filter.frequency.value = 2200 + energy * 3800;
  const m = { kind: 'synth' as const, timer: 0, next: c.currentTime + 0.1, step: 0, filter };
  m.timer = window.setInterval(() => {
    while (m.next < c.currentTime + 0.2) {
      scheduleStep(c, filter, m.step, m.next);
      m.next += STEP;
      m.step = (m.step + 1) % (8 * ROOTS.length);
    }
  }, 50);
  music = m;
}

export function stopMusic() {
  if (!music) return;
  const f = music.filter;
  if (music.kind === 'synth') window.clearInterval(music.timer);
  else music.src.stop(ctx ? ctx.currentTime + 1.5 : 0);
  window.setTimeout(() => f.disconnect(), 3000);
  music = null;
}
