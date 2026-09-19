/** Bot localhost API tunables -- mirrors backend/constants_bot.py. */
export const BOT_ACTION_KINDS = [
  'buy_market',
  'buy_limit_ask_offset',
  'sell_limit_bid_offset',
  'sell_limit_ask_offset',
  'exit_pos',
  'cancel_symbol',
  'exit_pos_pct',
  'sell_pos_pct_ask',
  'sell_pos_pct_bid_offset',
] as const;

export type BotActionKind = (typeof BOT_ACTION_KINDS)[number];

export const BOT_DEFAULT_MAX_SHARES = 1;
export const BOT_MAX_SHARES_CAP = 10;
export const BOT_BP_BUDGET_HARD_MAX_USD = 50;
export const BOT_BP_BUDGET_MIN_USD = 0.01;
export const BOT_BP_BUDGET_STEP_USD = 0.01;
export const BOT_DEFAULT_WORKING_TTL_SEC = 3;
export const BOT_WORKING_TTL_MIN_SEC = 1;
export const BOT_WORKING_TTL_MAX_SEC = 10;
export const BOT_ADVISE_DEFAULT_USD_CAP = 2;
export const BOT_ADVISE_DEFAULT_CALL_CAP = 10;
export const BOT_SOFT_BREAKER_USD = -50;
export const BOT_HARD_BREAKER_USD = -200;

export const BOT_AUTONOMY_LABEL = 'Bot Autonomy';
export const BOT_LEVEL_FIELD_LABEL = 'Level';
export const BOT_PACK_FIELD_LABEL = 'Pack';
export const BOT_LEVEL_LABELS = {
  0: 'Off',
  1: 'Eyes',
  2: 'Strategy',
} as const;
export const BOT_LEVEL_HINTS = {
  0: 'L0 dark -- no watch, propose, or writes',
  1: 'L1 Eyes -- watch and propose; human places',
  2: 'L2 Strategy -- live under gates after Activate',
} as const;
export const BOT_STATE_ACTIVE = 'Active';
export const BOT_STATE_NOT_ACTIVE = 'Not active';
export const BOT_ACTIVATE_LABEL = 'Activate';
export const BOT_DEACTIVATE_LABEL = 'Deactivate';
export const BOT_API_KEY_HINT = 'Need Nova API key to change Bot Autonomy';
export const BOT_API_KEY_SAVE = 'Save';
export const BOT_ERROR_NEED_API_KEY =
  'Need Nova API key -- Desktop and Vite read the same repo NOVA_API_KEY, or save it here';
export const BOT_ERROR_ARM_REQUIRED = 'Activate first, then choose Strategy';
export const BOT_ERROR_NOT_ACTIVE = 'Not active -- Activate before live fire';

export const BOT_PACK_HALT_LULD = 'halt-luld';
export const BOT_PACK_QUOTE_SPIKE = 'quote-spike';
export const BOT_PACK_VOLUME = 'volume';
export const BOT_PACK_LLM_DECIDE = 'llm-decide';
export const BOT_PACKS = [
  BOT_PACK_HALT_LULD,
  BOT_PACK_QUOTE_SPIKE,
  BOT_PACK_VOLUME,
  BOT_PACK_LLM_DECIDE,
] as const;
export type BotPackId = (typeof BOT_PACKS)[number];

export const BOT_PACK_LABELS: Record<BotPackId, string> = {
  'halt-luld': 'Halt / LULD resume',
  'quote-spike': 'Quote spike',
  volume: 'Volume boost',
  'llm-decide': 'LLM decide',
};

export const BOT_PACK_STUBS: readonly BotPackId[] = [];

export const BOT_QUOTE_SPIKE_MIN_PCT = 3;
export const BOT_QUOTE_SPIKE_WINDOW_SEC = 5;
export const BOT_QUOTE_SPIKE_COOLDOWN_SEC = 30;
export const BOT_VOLUME_MIN_MULT = 5;
export const BOT_VOLUME_WINDOW_SEC = 60;
export const BOT_VOLUME_BASELINE_SEC = 600;
export const BOT_VOLUME_COOLDOWN_SEC = 60;

export const BOT_PACK_DESCRIPTIONS: Record<BotPackId, string> = {
  'halt-luld':
    'When an allowlisted live-focus symbol resumes from halt or LULD, Eyes proposes and L2 plus Activate fires buy_market (or the configured kind) once, then waits the cooldown.',
  'quote-spike':
    `When an allowlisted live-focus last (or bid/ask mid when both sides exist) rises ${BOT_QUOTE_SPIKE_MIN_PCT}% within ${BOT_QUOTE_SPIKE_WINDOW_SEC}s on the shared L1/quote stream, Eyes proposes and L2 plus Activate fires buy_market (or spike_kind) once, then waits the cooldown. No new reqMktData.`,
  volume:
    `When an allowlisted live-focus day-volume rate over the last ${BOT_VOLUME_WINDOW_SEC}s is ${BOT_VOLUME_MIN_MULT}x the prior ${BOT_VOLUME_BASELINE_SEC}s baseline on the shared L1/quote stream, Eyes proposes and L2 plus Activate fires buy_market (or volume_kind) once, then waits the cooldown. Thin history fails closed. No new reqMktData.`,
  'llm-decide':
    'OpenRouter posts fixed-schema decisions from the Sensor Board snapshot for allowlisted live-focus names and live-fires those kinds only when L2 + Activate are on. Idle if OPENROUTER_API_KEY (or NOVA_LLM_API_KEY) is missing.',
};

export function packDescription(id: string): string {
  return BOT_PACK_DESCRIPTIONS[id as BotPackId] || '';
}

export function packStatus(id: string): 'live' | 'stub' {
  return (BOT_PACK_STUBS as readonly string[]).includes(id) ? 'stub' : 'live';
}

export function quoteSpikeSettingsLine(
  settings: Record<string, unknown> | undefined,
): string {
  const minPct = Number(settings?.min_pct ?? BOT_QUOTE_SPIKE_MIN_PCT);
  const windowSec = Number(settings?.window_sec ?? BOT_QUOTE_SPIKE_WINDOW_SEC);
  const kind = String(settings?.spike_kind || 'buy_market');
  const cool = Number(settings?.cooldown_sec ?? BOT_QUOTE_SPIKE_COOLDOWN_SEC);
  return `Signal: last or bid/ask mid up ${minPct}% in ${windowSec}s, fire ${kind} once, cooldown ${cool}s.`;
}

export function volumeSettingsLine(
  settings: Record<string, unknown> | undefined,
): string {
  const minMult = Number(settings?.min_mult ?? BOT_VOLUME_MIN_MULT);
  const windowSec = Number(settings?.window_sec ?? BOT_VOLUME_WINDOW_SEC);
  const baselineSec = Number(settings?.baseline_sec ?? BOT_VOLUME_BASELINE_SEC);
  const kind = String(settings?.volume_kind || 'buy_market');
  const cool = Number(settings?.cooldown_sec ?? BOT_VOLUME_COOLDOWN_SEC);
  return `Signal: last-${windowSec}s day-volume rate >= ${minMult}x the prior ${baselineSec}s baseline, fire ${kind} once, cooldown ${cool}s.`;
}

export const BOT_IN_CONTROL_LABEL = 'Bot is in control';

export const BOT_DESK_ARM_HEADER = 'X-Nova-Desk-Arm';
export const BOT_DESK_ARM_STORAGE = 'nova_bot_desk_arm';
export const BOT_ALLOWLIST_ADD = 'Add to bot allowlist';
export const BOT_ALLOWLIST_REMOVE = 'Remove from bot allowlist';
export const BOT_ALLOWLIST_HINT =
  'Right-click a scanner row, trader tab, or chart to add or remove. Empty list is fail-closed.';
export const BOT_ALLOWLIST_EMPTY = 'empty -- fail closed';
export const BOT_ALLOWLIST_ADD_LABEL = 'Add ticker';
export const BOT_ALLOWLIST_ADD_BUTTON = 'Add';
export const BOT_ALLOWLIST_CHIP_REMOVE = 'Remove';
/** Mirrors backend/constants_bot.py -- session.symbol_allowlist only, not caps.allowlist. */
export const BOT_SYMBOL_ALLOWLIST_CAP = 50;
export const BOT_ALLOWLIST_STRIP_LABEL = 'Allowlist';
export const BOT_ALLOWLIST_STRIP_TITLE = 'Symbol allowlist';

export function botAllowlistStripLabel(count: number): string {
  return `${BOT_ALLOWLIST_STRIP_LABEL} · ${count}`;
}
export const BOT_BREAKER_SOFT_LABEL = 'Bot trip $ (locked)';
export const BOT_BREAKER_HARD_LABEL = 'All-stop $ (locked)';
export const BOT_BREAKER_HINT =
  'Locked product thresholds. Session PATCH has no breaker fields. -$50 flattens and drops the bot to L0. -$200 flattens and locks bot plus manual buys until next ET midnight.';
