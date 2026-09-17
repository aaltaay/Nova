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
export const BOT_DEFAULT_WORKING_TTL_SEC = 3;
export const BOT_WORKING_TTL_MIN_SEC = 1;
export const BOT_WORKING_TTL_MAX_SEC = 10;
export const BOT_ADVISE_DEFAULT_USD_CAP = 2;
export const BOT_ADVISE_DEFAULT_CALL_CAP = 10;
export const BOT_SOFT_BREAKER_USD = -50;
export const BOT_HARD_BREAKER_USD = -200;

export const BOT_LEVEL_LABELS = {
  0: 'Off (L0 dark)',
  1: 'Eyes (L1 watch + propose)',
  2: 'Strategy (L2 small-cap)',
} as const;

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
  'quote-spike': 'Quote spike (stub)',
  volume: 'Volume boost (stub)',
  'llm-decide': 'LLM decide',
};

export const BOT_PACK_DESCRIPTIONS: Record<BotPackId, string> = {
  'halt-luld':
    'When an allowlisted live-focus symbol resumes from halt or LULD, Eyes proposes and L2 plus Activate fires buy_market (or the configured kind) once, then waits the cooldown.',
  'quote-spike':
    'Stub: quote-spike is not implemented yet -- the brain heartbeats only and fire returns 409 BOT_PACK_STUB.',
  volume:
    'Stub: volume-boost is not implemented yet -- the brain heartbeats only and fire returns 409 BOT_PACK_STUB.',
  'llm-decide':
    'A configured LLM posts fixed-schema proposals for allowlisted live-focus names and live-fires those kinds only when L2 + Activate are on. Idle if the key, base URL, or model is missing.',
};

export function packDescription(id: string): string {
  return BOT_PACK_DESCRIPTIONS[id as BotPackId] || '';
}

export const BOT_IN_CONTROL_LABEL = 'Bot is in control';

export const BOT_DESK_ARM_HEADER = 'X-Nova-Desk-Arm';
export const BOT_DESK_ARM_STORAGE = 'nova_bot_desk_arm';
export const BOT_ALLOWLIST_ADD = 'Add to bot allowlist';
export const BOT_ALLOWLIST_REMOVE = 'Remove from bot allowlist';
