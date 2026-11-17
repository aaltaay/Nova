/**
 * `GET /api/traders` on the demo desk (ADR 043, ADR 072; `architecture/schema/traders.md`): Nova Marketing Sample
 * Data with Claude and the brain both Off, holding nothing -- the demo has no AI trader, and its header says so
 * with "Brain · Off" from this answer, without a network request.
 */
const LIMITS = { max_shares: 1_000, risk_usd: 150, budget_usd: 25_000, budget_used_usd: 0, flat_by: '15:55' };

function offTrader(name: 'claude' | 'brain', short: string) {
  return {
    name, on: false, at: null, can_turn_on: true, why_not_on: null, done_for_today: false, state: 'off',
    text: `${short} · Off`, symbol: null, lane: { symbol: null, depth: false, tape: false, why: null },
    position: null, handed: [], today: { pnl: 0, loss_limit_usd: -500, tripped_at: null }, limits: { ...LIMITS },
    note: null,
  };
}

export function sampleTraders(nowS: number, venue: string) {
  return {
    schema_version: 1, generated_at: nowS, venue,
    traders: {
      claude: offTrader('claude', 'Claude'),
      brain: { ...offTrader('brain', 'Brain'), connected: false, reading: [], events: [] },
    },
    error: null,
  };
}
