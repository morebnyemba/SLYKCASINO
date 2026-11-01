// Shapes returned by /api/admin/risk/… (apps/risk/views.py).

export type Severity = 'low' | 'medium' | 'high' | 'critical';

export interface RiskSignal {
  id: number; code: string; severity: Severity; points: number; detail: string;
  data: Record<string, unknown>; linked_player_ids: number[]; created_at: string;
}

export interface RiskCase {
  id: number; player_id: number; username: string | null;
  status: 'open' | 'confirmed' | 'dismissed'; status_label: string;
  action: 'review' | 'suspended'; action_label: string; reason: string; score: number;
  created_at: string; updated_at: string; decided_at: string | null; decided_by: string; decision_note: string;
}

export interface RiskProfile {
  score: number; under_review: boolean; withdrawals_frozen: boolean; bonus_blocked: boolean; cleared_at: string | null;
}

export interface LinkedAccount { player_id: number; username: string | null; is_suspended: boolean | null; how: string[]; strong: boolean }

export interface RiskReport {
  generated_at: string;
  player: { id: number; username: string | null; email: string | null; created_at: string | null; kyc_status: string | null;
    is_suspended: boolean | null; suspended_reason: string };
  profile: RiskProfile;
  wallets: Record<'deposit' | 'bonus' | 'winnings', string>;
  signals: RiskSignal[];
  cases: RiskCase[];
  linked_accounts: LinkedAccount[];
  numbers: Record<string, string[]>;
  ips: string[];
  withdrawals: { id: number; amount: string; status: string; status_label: string; method_label: string;
    account_number: string; created_at: string; risk_hold?: boolean; risk_note?: string }[];
  transactions: { transaction_ref: string; kind: string; wallet: string; amount: string; reference: string; created_at: string }[];
}

export const SEVERITY_TONE: Record<Severity, 'slate' | 'gold' | 'red'> = {
  low: 'slate', medium: 'gold', high: 'red', critical: 'red',
};

/** Save the report as a JSON file — the "detailed fraud report" kept with the case. */
export function downloadReport(report: RiskReport, name: string) {
  const blob = new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `${name}.json`;
  a.click();
  URL.revokeObjectURL(url);
}
