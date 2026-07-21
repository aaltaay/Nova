/** Sample watchlist, decide, and signals for the isolated sample route. */
import type {
  NovaOsDecision,
  NovaOsGateResult,
  SetupSignal,
  WatchlistEntry,
} from '../strategy/types';

function pillars(symbol: string, pass: boolean): WatchlistEntry['five_pillars'] {
  const checks = [
    { name: 'Price', passed: true, detail: '$2–$20' },
    { name: 'Float', passed: true, detail: '<20M' },
    { name: 'RVOL', passed: pass, detail: pass ? '8x+' : '1.2x' },
    { name: 'Catalyst', passed: pass, detail: pass ? 'news' : 'weak' },
    { name: 'Trend', passed: true, detail: 'above VWAP' },
  ];
  const pass_count = checks.filter((c) => c.passed).length;
  return {
    symbol,
    all_pass: pass_count === checks.length,
    pass_count,
    total: checks.length,
    checkmark: pass_count === checks.length ? '✓' : `${pass_count}/5`,
    pillars: checks,
  };
}

export const SAMPLE_WATCHLIST: WatchlistEntry[] = [
  {
    symbol: 'SMPL',
    composite_score: 92,
    sub_scores: { change_pct: 95, relative_volume: 90, float: 88, catalyst: 94 },
    five_pillars: pillars('SMPL', true),
  },
  {
    symbol: 'GAPX',
    composite_score: 88,
    sub_scores: { change_pct: 98, relative_volume: 96, float: 92, catalyst: 80 },
    five_pillars: pillars('GAPX', true),
  },
  {
    symbol: 'MOMO',
    composite_score: 84,
    sub_scores: { change_pct: 85, relative_volume: 91, float: 86, catalyst: 70 },
    five_pillars: pillars('MOMO', true),
  },
  {
    symbol: 'NWSR',
    composite_score: 71,
    sub_scores: { change_pct: 72, relative_volume: 68, float: 75, catalyst: 55 },
    five_pillars: pillars('NWSR', false),
  },
  {
    symbol: 'RUNR',
    composite_score: 79,
    sub_scores: { change_pct: 90, relative_volume: 82, float: 70, catalyst: 65 },
    five_pillars: pillars('RUNR', true),
  },
];

function gate(
  name: string,
  passed: boolean,
  hard: boolean,
  reason_codes: string[],
  evidence: Record<string, unknown> = {},
): NovaOsGateResult {
  return { name, passed, hard, reason_codes, evidence };
}

function decision(
  symbol: string,
  verdict: 'BUY' | 'WAIT' | 'NO_BUY',
  confidence: number,
  opts: {
    catalystPass: boolean;
    impactClass: string;
    impactConf: number;
    reasons: string[];
    ticket?: boolean;
  },
): NovaOsDecision {
  const gates: NovaOsGateResult[] = [
    gate('universe', true, true, ['UNIVERSE_OK']),
    gate('session', true, true, ['SESSION_OK']),
    gate('setup', verdict !== 'NO_BUY', true, [
      verdict === 'NO_BUY' ? 'SETUP_MISS' : 'SETUP_GAP_AND_GO',
    ]),
    gate(
      'catalyst',
      opts.catalystPass,
      false,
      [opts.catalystPass ? 'CATALYST_STRONG' : 'CATALYST_WEAK'],
      {
        news_impact: {
          impact_class: opts.impactClass,
          confidence: opts.impactConf,
          age_bucket: 'fresh',
          price_reaction: opts.impactClass === 'moved_price' ? 'up' : 'flat',
          attention: 'elevated',
          source_tier: 'tier1',
          headline: `${symbol} sample catalyst headline`,
          headline_url: 'https://example.com/news',
          reasons: opts.reasons,
          ai_reasoning:
            symbol === 'SMPL'
              ? 'Informational Lincoln note — does not authorize size.'
              : null,
        },
      },
    ),
    gate('risk', true, true, ['RISK_OK']),
  ];
  const reason_codes = gates.flatMap((g) => g.reason_codes).filter((c) => !c.endsWith('_OK'));
  return {
    symbol,
    decision: verdict,
    reason_codes: reason_codes.length ? reason_codes : ['ALL_GATES_PASS'],
    mode: 'signal',
    requested_mode: 'signal',
    setup: 'gap_and_go',
    ticket: opts.ticket
      ? {
          entry: 4.2,
          stop: 3.9,
          target: 5.1,
          shares: 250,
          r_multiple: 2.5,
          risk_dollars: 75,
        }
      : null,
    confidence,
    gates,
    citations: ['sample.fixture', 'news.impact'],
    would_execute: false,
    executed: false,
    policy_version: 'sample-v1',
    receipt: {
      id: null,
      policy_version: 'sample-v1',
      kind: 'decision',
      symbol,
      decision: verdict,
      action: null,
      mode: 'signal',
      reason_codes,
      would_execute: false,
      executed: false,
      payload: { sample: true },
    },
    note: 'Sample decision — demo only',
  };
}

export const SAMPLE_DECISIONS: NovaOsDecision[] = [
  decision('SMPL', 'BUY', 0.82, {
    catalystPass: true,
    impactClass: 'moved_price',
    impactConf: 0.86,
    reasons: ['price_reacted_up', 'high_confidence'],
    ticket: true,
  }),
  decision('GAPX', 'WAIT', 0.58, {
    catalystPass: false,
    impactClass: 'attention_only',
    impactConf: 0.4,
    reasons: ['headline_attention', 'waiting_confirmation'],
    ticket: true,
  }),
  decision('MOMO', 'WAIT', 0.52, {
    catalystPass: false,
    impactClass: 'attention_only',
    impactConf: 0.35,
    reasons: ['social_attention_only'],
    ticket: true,
  }),
  decision('NWSR', 'NO_BUY', 0.2, {
    catalystPass: false,
    impactClass: 'insufficient_data',
    impactConf: 0.15,
    reasons: ['thin_news'],
    ticket: false,
  }),
];

export const SAMPLE_SIGNALS: SetupSignal[] = [
  {
    symbol: 'SMPL',
    setup: 'gap_and_go',
    eligible: true,
    would_execute: false,
    triggered: true,
    current_price: 4.25,
    entry_price: 4.2,
    stop_price: 3.9,
    target_price: 5.1,
    five_pillars: pillars('SMPL', true),
    notes: ['Sample Gap & Go trigger'],
    timestamp: Date.now() / 1000 - 120,
    nova_os: {
      decision: 'BUY',
      reason_codes: ['CATALYST_STRONG'],
      mode: 'signal',
      would_execute: false,
      receipt_id: null,
    },
  },
  {
    symbol: 'GAPX',
    setup: 'bull_flag',
    eligible: true,
    would_execute: false,
    triggered: true,
    current_price: 1.92,
    entry_price: 1.88,
    stop_price: 1.7,
    target_price: 2.3,
    five_pillars: pillars('GAPX', true),
    notes: ['Sample bull flag'],
    timestamp: Date.now() / 1000 - 300,
    nova_os: {
      decision: 'WAIT',
      reason_codes: ['CATALYST_WEAK'],
      mode: 'signal',
      would_execute: false,
    },
  },
];

export function sampleDecisionForSymbol(symbol: string): NovaOsDecision | null {
  const key = symbol.trim().toUpperCase();
  return SAMPLE_DECISIONS.find((d) => d.symbol === key) ?? null;
}
