'use client';

import { useEffect, useState } from 'react';
import { FaPalette } from 'react-icons/fa';
import { Card, CardContent, CardHeader, CardTitle } from '@slyk/ui/components/card';
import { useAuth } from '@/lib/auth-context';
import { useApi } from '@/lib/use-api';
import { config } from '@/lib/config';

type Tokens = Record<string, string>;

interface ThemeResponse {
  light: Tokens;
  dark: Tokens;
  updated_at?: string;
  updated_by_username?: string;
}

interface IdentityResponse {
  site_name: string;
  tagline: string;
  logo_url: string;
  license_text: string;
  updated_at?: string;
  updated_by_username?: string;
}

const DEFAULT_IDENTITY: IdentityResponse = {
  site_name: 'SLÝKBETS',
  tagline: 'Bet smart. Brag often.',
  logo_url: '',
  license_text: 'Licensed and regulated by the Lotteries and Gaming Board of Zimbabwe. Licence No. LGB/SLYKBETS/2026 (demo).',
};

// Keep in sync with backend/apps/branding/tokens.py.
const DEFAULT_LIGHT: Tokens = {
  background: '#F3F4FC', foreground: '#1A1538',
  card: '#FFFFFF', card_foreground: '#1A1538',
  primary: '#312783', primary_foreground: '#FFFFFF',
  secondary: '#4338CA', secondary_foreground: '#FFFFFF',
  muted: '#E6E5F7', muted_foreground: '#5C5A86',
  accent: '#5B53D6', accent_foreground: '#FFFFFF',
  gold: '#B8860B', gold_foreground: '#FFFFFF',
  ring: '#312783', border: '#C9CBEC', input: '#ECEDF8',
  destructive: '#DC2626',
  live: '#DC2626', live_foreground: '#FFFFFF',
  tier_bronze: '#92400E', tier_bronze_foreground: '#92400E',
  tier_silver: '#6B7280', tier_silver_foreground: '#6B7280',
  win: '#15924E', win_foreground: '#FFFFFF',
  down: '#DC2626',
  chip: '#ECEDF8', chip_foreground: '#1A1538',
};

const DEFAULT_DARK: Tokens = {
  background: '#0C0820', foreground: '#F2F1FB',
  card: '#191347', card_foreground: '#F2F1FB',
  primary: '#312783', primary_foreground: '#FFFFFF',
  secondary: '#6C63E8', secondary_foreground: '#FFFFFF',
  muted: '#1E1850', muted_foreground: '#9D99C8',
  accent: '#8079EE', accent_foreground: '#FFFFFF',
  gold: '#E6B84C', gold_foreground: '#1A1538',
  ring: '#6C63E8', border: 'rgba(255, 255, 255, 0.09)', input: '#1E1850',
  destructive: '#FF6B6B',
  live: '#FF5260', live_foreground: '#FFFFFF',
  tier_bronze: '#92400E', tier_bronze_foreground: '#92400E',
  tier_silver: '#6B7280', tier_silver_foreground: '#6B7280',
  win: '#36D399', win_foreground: '#0C0820',
  down: '#FF6B6B',
  chip: '#1E1850', chip_foreground: '#F2F1FB',
};

const GROUPS: { title: string; keys: (keyof Tokens)[] }[] = [
  { title: 'Surfaces', keys: ['background', 'foreground', 'card', 'card_foreground'] },
  { title: 'Primary / Secondary / Accent', keys: ['primary', 'primary_foreground', 'secondary', 'secondary_foreground', 'accent', 'accent_foreground'] },
  { title: 'Gold (VIP & CTAs)', keys: ['gold', 'gold_foreground'] },
  { title: 'Borders, Inputs & Focus Ring', keys: ['border', 'input', 'ring'] },
  { title: 'Live / Win / Down / Destructive', keys: ['live', 'live_foreground', 'win', 'win_foreground', 'down', 'destructive'] },
  { title: 'Loyalty Tiers', keys: ['tier_bronze', 'tier_bronze_foreground', 'tier_silver', 'tier_silver_foreground'] },
  { title: 'Chips & Pills', keys: ['chip', 'chip_foreground'] },
];

function labelFor(key: string): string {
  return key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

function ColorField({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  const isHex6 = /^#[0-9a-fA-F]{6}$/.test(value);
  return (
    <div className="flex items-center gap-2">
      <input
        type="color"
        value={isHex6 ? value : '#000000'}
        onChange={(e) => onChange(e.target.value)}
        title={isHex6 ? 'Pick a color' : 'Native picker only supports hex — edit the text field for rgba()/hsla()'}
        className="h-8 w-8 shrink-0 cursor-pointer rounded-md border border-border bg-transparent p-0"
      />
      <div className="min-w-0 flex-1">
        <label className="block truncate text-[11px] font-medium text-muted-foreground">{label}</label>
        <input
          type="text"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          spellCheck={false}
          className="w-full rounded-md border border-border bg-background px-2 py-1 font-mono text-xs focus:outline-none focus:ring-2 focus:ring-primary"
        />
      </div>
    </div>
  );
}

function ThemeColumn({
  title, tokens, onChange, onReset,
}: {
  title: string; tokens: Tokens; onChange: (key: string, value: string) => void; onReset: () => void;
}) {
  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-bold">{title}</h2>
        <button onClick={onReset} className="text-xs font-medium text-muted-foreground hover:text-foreground">
          Reset to defaults
        </button>
      </div>
      {GROUPS.map((g) => (
        <div key={g.title} className="space-y-2">
          <p className="text-[10.5px] font-bold uppercase tracking-wide text-muted-foreground/70">{g.title}</p>
          <div className="grid gap-2 sm:grid-cols-2">
            {g.keys.map((k) => (
              <ColorField key={k} label={labelFor(k)} value={tokens[k] ?? ''} onChange={(v) => onChange(k, v)} />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

/** A tiny live mock of a header/card/buttons driven by the in-progress form values. */
function PreviewCard({ title, tokens }: { title: string; tokens: Tokens }) {
  return (
    <div className="overflow-hidden rounded-2xl border" style={{ borderColor: tokens.border, background: tokens.background }}>
      <div
        className="flex items-center justify-between px-4 py-3"
        style={{ background: `linear-gradient(90deg, ${tokens.primary}, ${tokens.secondary})` }}
      >
        <span className="text-xs font-extrabold tracking-wide" style={{ color: tokens.primary_foreground }}>{title} preview</span>
        <span
          className="rounded-md px-2.5 py-1 text-[11px] font-bold"
          style={{ background: tokens.gold, color: tokens.gold_foreground }}
        >
          Deposit
        </span>
      </div>
      <div className="space-y-2.5 p-4">
        <div className="rounded-xl p-3" style={{ background: tokens.card, color: tokens.card_foreground, border: `1px solid ${tokens.border}` }}>
          <p className="text-sm font-bold">Card surface</p>
          <p className="text-xs" style={{ color: tokens.muted_foreground }}>Muted supporting text</p>
          <div className="mt-2 flex flex-wrap gap-1.5">
            <span className="rounded-full px-2 py-0.5 text-[10px] font-bold" style={{ background: tokens.live, color: tokens.live_foreground }}>LIVE</span>
            <span className="rounded-full px-2 py-0.5 text-[10px] font-bold" style={{ background: tokens.win, color: tokens.win_foreground }}>+24.80</span>
            <span className="rounded-full px-2 py-0.5 text-[10px] font-bold" style={{ background: tokens.chip, color: tokens.chip_foreground }}>97.5%</span>
          </div>
        </div>
        <button
          className="w-full rounded-lg px-3 py-2 text-xs font-bold"
          style={{ background: tokens.primary, color: tokens.primary_foreground }}
        >
          Primary action
        </button>
      </div>
    </div>
  );
}

function IdentitySection() {
  const { accessToken } = useAuth();
  const { data, loading, error, refetch } = useApi<IdentityResponse>('/branding/identity/');

  const [form, setForm] = useState<IdentityResponse>(DEFAULT_IDENTITY);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState('');
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (data) setForm(data);
  }, [data]);

  const set = (k: keyof IdentityResponse, v: string) => setForm((f) => ({ ...f, [k]: v }));

  async function handleSave() {
    if (!accessToken) return;
    setSaving(true);
    setSaveError('');
    setSaved(false);
    const res = await fetch(`${config.apiUrl}/branding/identity/`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${accessToken}` },
      body: JSON.stringify({
        site_name: form.site_name,
        tagline: form.tagline,
        logo_url: form.logo_url,
        license_text: form.license_text,
      }),
    });
    setSaving(false);
    if (!res.ok) {
      const json = await res.json().catch(() => ({}));
      setSaveError(JSON.stringify(json) ?? `API ${res.status}`);
      return;
    }
    setSaved(true);
    refetch();
    setTimeout(() => setSaved(false), 3000);
  }

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between space-y-0">
        <CardTitle className="text-base">Site identity</CardTitle>
        <button
          onClick={handleSave}
          disabled={saving || loading}
          className="rounded-md bg-gradient-to-br from-gold to-gold/70 px-4 py-1.5 text-xs font-bold text-gold-foreground shadow transition-transform hover:scale-[1.02] disabled:opacity-50"
        >
          {saving ? 'Saving…' : 'Save identity'}
        </button>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="text-xs text-muted-foreground">
          The site name, logo, tagline, and gambling licence text shown across the header, footer, login screen, and age gate.
        </p>
        {loading && <p className="text-sm text-muted-foreground">Loading…</p>}
        {error && <p className="text-sm text-red-500">Failed to load: {error}</p>}
        {saveError && <p className="text-sm text-red-500">Failed to save: {saveError}</p>}
        {saved && <p className="text-sm font-medium text-win">Saved — live on next page load.</p>}

        {!loading && (
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1">
              <label className="text-sm font-medium">Site name</label>
              <input
                value={form.site_name}
                onChange={(e) => set('site_name', e.target.value)}
                placeholder="SLÝKBETS"
                className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
              />
            </div>
            <div className="space-y-1">
              <label className="text-sm font-medium">Tagline</label>
              <input
                value={form.tagline}
                onChange={(e) => set('tagline', e.target.value)}
                placeholder="Bet smart. Brag often."
                className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
              />
            </div>
            <div className="space-y-1 sm:col-span-2">
              <label className="text-sm font-medium">Logo URL (optional)</label>
              <div className="flex items-center gap-3">
                <input
                  value={form.logo_url}
                  onChange={(e) => set('logo_url', e.target.value)}
                  placeholder="https://…/logo.png (leave blank to use the default text mark)"
                  className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
                />
                {form.logo_url && (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={form.logo_url} alt="Logo preview" className="h-9 w-auto max-w-[120px] shrink-0 rounded border border-border object-contain bg-white p-1" />
                )}
              </div>
            </div>
            <div className="space-y-1 sm:col-span-2">
              <label className="text-sm font-medium">Licence &amp; regulator text</label>
              <textarea
                value={form.license_text}
                onChange={(e) => set('license_text', e.target.value)}
                rows={3}
                className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
              />
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export default function BrandingPage() {
  const { accessToken } = useAuth();
  const { data, loading, error, refetch } = useApi<ThemeResponse>('/branding/theme/');

  const [light, setLight] = useState<Tokens>(DEFAULT_LIGHT);
  const [dark, setDark] = useState<Tokens>(DEFAULT_DARK);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState('');
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (data?.light) setLight(data.light);
    if (data?.dark) setDark(data.dark);
  }, [data]);

  async function handleSave() {
    if (!accessToken) return;
    setSaving(true);
    setSaveError('');
    setSaved(false);
    const res = await fetch(`${config.apiUrl}/branding/theme/`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${accessToken}` },
      body: JSON.stringify({ light, dark }),
    });
    setSaving(false);
    if (!res.ok) {
      const json = await res.json().catch(() => ({}));
      setSaveError((json as { detail?: string }).detail ?? `API ${res.status}`);
      return;
    }
    setSaved(true);
    refetch();
    setTimeout(() => setSaved(false), 3000);
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <span className="flex h-8 w-8 items-center justify-center rounded-full bg-gold/15 text-gold">
            <FaPalette size={13} />
          </span>
          <div>
            <h1 className="text-2xl font-bold">Branding</h1>
            <p className="text-sm text-muted-foreground">
              Site name, logo, licence text, and site-wide colors for headers, footers, cards, casino & sportsbook displays, and modals. Changes go live immediately after saving.
            </p>
          </div>
        </div>
      </div>

      <IdentitySection />

      <div className="flex items-center justify-between">
        <h2 className="text-lg font-bold">Colors</h2>
        <button
          onClick={handleSave}
          disabled={saving || loading}
          className="rounded-md bg-gradient-to-br from-gold to-gold/70 px-5 py-2 text-sm font-bold text-gold-foreground shadow transition-transform hover:scale-[1.02] disabled:opacity-50"
        >
          {saving ? 'Saving…' : 'Save theme'}
        </button>
      </div>

      {loading && <p className="text-sm text-muted-foreground">Loading current theme…</p>}
      {error && <p className="text-sm text-red-500">Failed to load theme: {error}</p>}
      {saveError && <p className="text-sm text-red-500">Failed to save: {saveError}</p>}
      {saved && <p className="text-sm font-medium text-win">Saved — the player site will reflect this on next load.</p>}

      {!loading && (
        <div className="grid gap-6 xl:grid-cols-2">
          <Card>
            <CardHeader><CardTitle className="text-base">Light theme</CardTitle></CardHeader>
            <CardContent className="space-y-5">
              <PreviewCard title="Light" tokens={light} />
              <ThemeColumn title="Light theme tokens" tokens={light} onReset={() => setLight(DEFAULT_LIGHT)} onChange={(k, v) => setLight((t) => ({ ...t, [k]: v }))} />
            </CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle className="text-base">Dark theme</CardTitle></CardHeader>
            <CardContent className="space-y-5">
              <PreviewCard title="Dark" tokens={dark} />
              <ThemeColumn title="Dark theme tokens" tokens={dark} onReset={() => setDark(DEFAULT_DARK)} onChange={(k, v) => setDark((t) => ({ ...t, [k]: v }))} />
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
