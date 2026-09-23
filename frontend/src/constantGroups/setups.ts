/** Setup scanner UI (ADR 022). The backend owns the rules (`backend/constants_setups.py`). */

export const SETUPS_WS_PATH = '/ws/setups';
export const SETUPS_SCOREBOARD_PATH = '/api/setups/scoreboard';
export const SETUPS_RECONNECT_MAX_MS = 30_000;
export const SETUPS_SCOREBOARD_POLL_MS = 30_000;
export const SETUPS_SCOREBOARD_DAYS = [1, 5, 20, 0] as const;   // 0 = all
export const SETUPS_SOUND_STORAGE_KEY = 'nova.setups.sound.v1';
export const SETUPS_PING_HZ = 1175;
export const SETUPS_PING_GAIN = 0.05;
export const SETUPS_PING_SEC = 0.22;
/** A staged ticket waits this long for the Trader tab's ticket to mount. */
export const SETUPS_STAGE_TICKET_DELAY_MS = 400;

export const SETUP_STATE_LABELS: Record<string, string> = {
  near: 'Near',
  armed: 'Armed',
  triggered: 'Triggered',
  pullback: 'Pulling back',
  leg: 'Leg up',
  failed: 'Failed',
  watching: 'Watching',
};

export const SETUP_STATE_TITLES: Record<string, string> = {
  near: 'Price is within a few cents of the trigger: read the tape now.',
  armed: 'Pullback is in place. The trigger and stop are known; waiting for price to come back up.',
  triggered: 'Price traded over the trigger. The scoreboard is now tracking what it did.',
  pullback: 'A pullback is forming but one rule blocks it (MACD, risk size or time of day). The reason says which.',
  leg: 'A fresh high on a 5%+ leg. Wait for the first pullback.',
  failed: 'The pullback broke a rule (closed under the 9 EMA, gave back half the leg, or ran too long).',
  watching: 'Nothing to act on.',
};

export const SETUP_KIND_LABELS: Record<string, string> = {
  first_pullback: 'First pullback',
  second_pullback: 'Second pullback',
};

export const TAPE_VERDICT_LABELS: Record<string, string> = {
  go: 'Tape: go',
  wait: 'Tape: wait',
  veto: 'Tape: no',
  blind: 'Tape: blind',
};

export const TAPE_VERDICT_TITLES: Record<string, string> = {
  go: 'Green on the tape and no seller holding the level. The bot would take this.',
  wait: 'Not yet: a seller at the level that is not thinning, a burst of red, or no green on the tape.',
  veto: 'No: spread too wide, a 100k+ seller at the level, or a hidden seller soaking up the buying.',
  blind: 'Nova holds no Level 2 line for this symbol. Open it in the Trader so the bot can read the tape.',
};

/* Catalyst labels (CATALYST_CATEGORY_LABELS / CATALYST_VERDICT_TITLES) live in constantGroups/catalysts.ts. */

/** Scoreboard splits, in the order they answer the question: does the tape
 * gate turn the bar shape into a winning trade? */
export const SETUPS_SPLIT_TITLES: Record<string, string> = {
  tape_at_trigger: 'Tape at the trigger',
  grade: 'Grade when armed',
  session: 'Session',
  kind: 'Setup',
};

export const SETUPS_SPLIT_KEY_LABELS: Record<string, Record<string, string>> = {
  tape_at_trigger: {
    go: 'Tape said go',
    wait: 'Tape said wait',
    veto: 'Tape said no',
    blind: 'No Level 2 line',
    none: 'Never triggered',
  },
  grade: { A: 'Grade A', B: 'Grade B', C: 'Grade C', '?': 'No grade' },
  session: { premarket: 'Premarket (before 9:30)', regular: 'Regular hours', unknown: 'Unknown' },
  kind: { first_pullback: 'First pullback', second_pullback: 'Second pullback', '?': 'Unknown' },
};

export const SETUPS_DAYS_LABELS: Record<number, string> = { 1: 'Today', 5: '5 days', 20: '20 days', 0: 'All' };
