/**
 * "Can Nova trade right now?" in one line, for every ticker at once (ADR 044). The checks that hold for
 * every stock -- the Bot switch (the header's), the Strategy Bots key, the desk, a strategy at On, the windows, the
 * day's cap -- are named with their fix when one stops it; otherwise it names the tickers that are ready. Each ticker's own answer is
 * in Tickers today below and in its Trader tab's Who trades row. The desk's checks sit under it as chips,
 * then what a short needs (ADR 049, #778 step 5): a margin account, $2,000 of equity, the short hours and
 * Live -- they hold the short strategies only, never a long.
 */
import { tipProps } from '../ux';
import { ownStrategySetups } from './botLevels';
import { botOn, offWords } from './botSwitch';
import { gateLine, type GateContext } from './botGateWords';
import { prose } from './botsPageFormat';
import type { TriggersView } from './triggersApi';
import type { BotSession, ShortChip } from './types';

/** The gates that hold for every stock at once: one of them closed means no ticker can be bought. */
const DESK_WIDE = ['venue', 'padlock', 'strategy_key', 'kill_switch', 'loss_limit', 'commissions', 'setups', 'window',
  'daily_cap', 'extended_hours'];
const CHIPS: [string, string][] = [['venue', 'Venue'], ['padlock', 'Padlock'], ['kill_switch', 'Orders not frozen'], ['loss_limit', 'Under loss limit']];
/** The short chips (``GET /api/bot/session`` ``shorts``), in the spec's order. */
const SHORT_CHIPS: [keyof NonNullable<BotSession['shorts']>, string][] = [
  ['margin_account', 'Margin account'], ['equity', 'Equity ≥ $2,000'], ['hours', 'Shorts until 15:50'],
  ['live', 'Live shorts: operator-controlled'],
];
const SHORT_UNREAD = 'This backend does not report what a short needs (it predates #778 step 5).';

export type AnswerFix = 'bot' | 'key' | 'strategies' | 'unlock';
export interface AnswerReason { id: string; text: string; fix: { kind: AnswerFix; label: string } | null }

/** The gates read from the strategies' effective levels: while the Bot is off the master is at Eyes, so they
 * read closed whatever the strategies are -- the switch is the reason then, said once. */
const FROM_EFFECTIVE = new Set(['setups', 'window']);

/** Every stock-wide reason Nova cannot buy now, the Bot switch first. */
export function answerReasons(session: BotSession, ctx: GateContext): AnswerReason[] {
  const out: AnswerReason[] = [];
  const on = botOn(session);
  if (!on) out.push({ id: 'bot', text: `the Bot is off: ${offWords(session)}`, fix: { kind: 'bot', label: 'Turn on in the header' } });
  if (!on && !ownStrategySetups(session).length) {
    out.push({ id: 'setups', text: 'No strategy is at On: set one to On on its card.', fix: { kind: 'strategies', label: 'Set one to On' } });
  }
  for (const g of session.gates ?? []) {
    if (g.ok || !DESK_WIDE.includes(g.id) || (!on && FROM_EFFECTIVE.has(g.id))) continue;
    const line = gateLine(g, ctx);
    const text = prose(line.why ?? line.text);
    const fix = g.id === 'window' || g.id === 'setups' ? { kind: 'strategies' as const, label: g.id === 'window' ? 'Widen a window' : 'Set one to On' }
      : g.id === 'padlock' ? { kind: 'unlock' as const, label: 'Unlock the padlock' }
        : g.id === 'strategy_key' ? { kind: 'key' as const, label: 'Turn it on above' } : null;
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
    // The Bot switch is in the header (2026-10-15): the fix takes you to it; the Strategy Bots key is atop this page.
    else if (kind === 'bot') document.querySelector<HTMLElement>('[data-testid="global-bar-bot-key"]')?.focus();
    else if (kind === 'key') document.querySelector<HTMLElement>('[data-testid="bot-key-strategy-switch"]')?.focus();
    else scrollTo(strategiesAnchor);
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
      <div className="bots-answer__q">Can Nova trade right now?</div>
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
      <div className="bots-answer__chips bots-answer__chips--short" data-testid="bots-answer-shorts">
        <span className="bots-answer__label">▼ SHORT needs</span>
        {SHORT_CHIPS.map(([id, label]) => {
          const chip = session.shorts?.[id] as ShortChip | undefined;
          const ok = chip ? chip.ok : null;
          const tip = chip ? prose(chip.text) : session.shorts?.error ?? SHORT_UNREAD;
          return (
            <span key={id} className={`bots-answer__chip${ok === false ? ' is-no' : ok ? ' is-ok' : ''}`}
              {...tipProps(tip, label)} data-testid={`bots-answer-short-${id}`}>
              <i className="bots-answer__dot" aria-hidden="true" />{label}
            </span>
          );
        })}
      </div>
    </section>
  );
}
