/**
 * "Can Nova buy right now?" in one line, for every ticker at once (ADR 043). The checks that hold for
 * every stock -- the Bot switch, the desk, a strategy at On, the windows, the day's cap -- are named with
 * their fix when one stops it; otherwise it names the tickers that are ready. Each ticker's own answer is
 * in Tickers today below and in its Trader tab's Who trades row. The desk's checks sit under it as chips.
 */
import { BOTS_VENUE_NAMES, botsDayLocked } from '../constantGroups/bots_page';
import { tipProps } from '../ux';
import { BOT_CARD_ANCHOR } from './BotSwitchCard';
import { botOn, offWords } from './botSwitch';
import { gateLine, type GateContext } from './botGateWords';
import { prose } from './botsPageFormat';
import { etTime, etUntil, usdCents } from './botWhen';
import type { TriggersView } from './triggersApi';
import type { BotSession } from './types';

/** The gates that hold for every stock at once: one of them closed means no ticker can be bought. */
const DESK_WIDE = ['venue', 'padlock', 'kill_switch', 'day_lock', 'commissions', 'setups', 'window', 'daily_cap', 'extended_hours'];
const CHIPS: [string, string][] = [['venue', 'Venue'], ['padlock', 'Padlock'], ['kill_switch', 'Orders not frozen'], ['day_lock', 'All-stop clear']];

export type AnswerFix = 'bot' | 'strategies' | 'unlock';
export interface AnswerReason { id: string; text: string; fix: { kind: AnswerFix; label: string } | null }

/** The all-stop in full: when, at what P&L, and that it locks your own buys too. */
function dayLockWords(session: BotSession): string | null {
  const lock = session.day_lock;
  if (!lock?.active && !session.day_lock_active) return null;
  const venue = BOTS_VENUE_NAMES[String(lock?.venue ?? session.breakers?.venue ?? '')] ?? 'this venue';
  return botsDayLocked(venue, etTime(lock?.tripped_at ?? null), usdCents(lock?.pnl ?? null),
    etUntil(lock?.until ?? session.hard_lock_until_date));
}

/** Every stock-wide reason Nova cannot buy now, the Bot switch first. */
export function answerReasons(session: BotSession, ctx: GateContext): AnswerReason[] {
  const out: AnswerReason[] = [];
  if (!botOn(session)) out.push({ id: 'bot', text: `the Bot is off: ${offWords(session)}`, fix: { kind: 'bot', label: 'Turn on…' } });
  for (const g of session.gates ?? []) {
    if (g.ok || !DESK_WIDE.includes(g.id)) continue;
    const line = gateLine(g, ctx);
    const text = (g.id === 'day_lock' ? dayLockWords(session) : null) ?? prose(line.why ?? line.text);
    const fix = g.id === 'window' || g.id === 'setups' ? { kind: 'strategies' as const, label: g.id === 'window' ? 'Widen a window' : 'Set one to On' }
      : g.id === 'padlock' ? { kind: 'unlock' as const, label: 'Unlock the padlock' } : null;
    out.push({ id: g.id, text, fix });
  }
  return out;
}

function scrollTo(id: string) {
  document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

export function BotAnswerLine({ session, ctx, triggers, strategiesAnchor, onUnlock }: {
  session: BotSession;
  ctx: GateContext;
  triggers: TriggersView | null;
  strategiesAnchor: string;
  /** The padlock's own unlock (Paper and Sim in one click; Live asks for the PIN). */
  onUnlock: () => void;
}) {
  const fixIt = (kind: AnswerFix) => {
    if (kind === 'unlock') onUnlock();
    else scrollTo(kind === 'bot' ? BOT_CARD_ANCHOR : strategiesAnchor);
  };
  const reasons = answerReasons(session, ctx);
  const ready = (triggers?.tickers ?? []).filter(t => t.now?.answer === 'yes').map(t => t.symbol);
  const listed = (triggers?.tickers ?? []).filter(t => t.listed).length;
  const headline = reasons.length
    ? 'No, on any ticker:'
    : ready.length
      ? `Yes, on ${ready.join(', ')}: at the next go trigger`
      : listed
        ? 'No ticker is ready: each one says why below'
        : 'No: today\'s hot list is empty';
  const gates = new Map((session.gates ?? []).map(g => [g.id, g]));
  return (
    <section className="bots-card bots-answer" data-testid="bots-answer">
      <div className="bots-answer__q">Can Nova buy right now?</div>
      <div className="bots-answer__row">
        <span className={`bots-answer__a${reasons.length || !ready.length ? ' is-no' : ' is-yes'}`} data-testid="bots-answer-headline">
          <i className="bots-answer__dot" aria-hidden="true" />{headline}
        </span>
        {reasons.map(r => (
          <span key={r.id} className="bots-answer__why" data-testid={`bots-answer-${r.id}`}>
            <i className="bots-answer__dot is-no" aria-hidden="true" />
            {r.text}
            {r.fix ? (
              <button type="button" className="bots-linkbtn" data-testid={`bots-answer-fix-${r.id}`}
                onClick={() => fixIt(r.fix!.kind)}>{r.fix.label}</button>
            ) : null}
          </span>
        ))}
      </div>
      <div className="bots-answer__chips">
        {CHIPS.map(([id, label]) => {
          const g = gates.get(id);
          const ok = g ? g.ok : null;
          return (
            <span key={id} className={`bots-answer__chip${ok === false ? ' is-no' : ok ? ' is-ok' : ''}`}
              {...(g ? tipProps(prose(gateLine(g, ctx).tip)) : tipProps('This backend does not report it.'))}
              data-testid={`bots-answer-chip-${id}`}>
              <i className="bots-answer__dot" aria-hidden="true" />{label}
            </span>
          );
        })}
        <span className="bots-answer__note">Each ticker's own answer is in Tickers today below, and in the Who trades row on its Trader tab.</span>
      </div>
    </section>
  );
}
