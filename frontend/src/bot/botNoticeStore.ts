/**
 * The bot's notices (ADR 042, the visibility rule): whatever Nova refused or did on
 * the bot's behalf that the operator might not see where they clicked -- a refused
 * "Let the bot trade", Nova's working entries cancelled when the desk left a venue
 * -- as a toast in the window that asked. One store per window, in memory; it
 * imports nothing, so the venue pill and any ticker list can raise one through the
 * bot barrel without pulling in the Bots page. A refusal stays until dismissed;
 * anything else leaves on its own (bot/BotNotices.tsx).
 */
export type BotNoticeTone = 'ok' | 'info' | 'warn' | 'bad';

export interface BotNotice {
  id: number;
  tone: BotNoticeTone;
  title: string;
  text: string;
  at: number;
}

/** At most this many on screen; the oldest goes first. */
const MAX_NOTICES = 6;

let seq = 0;
let notices: readonly BotNotice[] = [];
const listeners = new Set<() => void>();

function emit(): void {
  listeners.forEach(fn => fn());
}

export function pushBotNotice(notice: { tone: BotNoticeTone; title: string; text: string }): number {
  seq += 1;
  const next: BotNotice = { id: seq, at: Date.now(), ...notice };
  notices = [...notices, next].slice(-MAX_NOTICES);
  emit();
  return next.id;
}

export function dismissBotNotice(id: number): void {
  if (!notices.some(n => n.id === id)) return;
  notices = notices.filter(n => n.id !== id);
  emit();
}

export function getBotNotices(): readonly BotNotice[] {
  return notices;
}

export function subscribeBotNotices(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

const VENUE_NAMES: Record<string, string> = { live: 'Live', paper: 'Paper', sim: 'Sim' };
const BY_WORDS: Record<string, string> = { bot: 'The bot\'s', auto_entry: 'Auto-entry\'s', approve: 'Your approved' };

/**
 * `POST /api/desk/venue`'s `left` (ADR 042 F): Nova's working entries cancelled on the
 * venue the desk left, before it flipped -- one notice each. Anything else is ignored.
 */
export function noticeVenueLeft(left: unknown): number {
  if (!Array.isArray(left)) return 0;
  let n = 0;
  for (const raw of left) {
    if (!raw || typeof raw !== 'object') continue;
    const row = raw as Record<string, unknown>;
    const symbol = typeof row.symbol === 'string' ? row.symbol : '?';
    const venue = VENUE_NAMES[String(row.venue ?? '')] ?? String(row.venue ?? 'the venue it left');
    const order = typeof row.order_id === 'number' ? ` #${row.order_id}` : '';
    const own = typeof row.text === 'string' && row.text.trim() ? row.text.trim().replace(/ -- /g, ' — ') : null;
    pushBotNotice({
      tone: 'warn',
      title: `Cancelled ${symbol} on ${venue}`,
      text: own ?? `${BY_WORDS[String(row.by ?? '')] ?? 'Nova\'s'} working entry${order} on ${symbol} was cancelled when the desk left ${venue}.`,
    });
    n += 1;
  }
  return n;
}

export function _resetBotNoticesForTests(): void {
  notices = [];
  seq = 0;
  emit();
}
