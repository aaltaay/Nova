/**
 * One TraderTV host's bot, in the middle of the host's card on Bots > LiveTrader Bots (ADR 055; operator 2026-10-15:
 * "all of this none sense Entry you/bot exit you/bot .. can all be compacted inside these empty spaces... includeing
 * bot keys", approved from a render). Two lines: its key, Entry, Exit and Rules; then its allowance, today and skips,
 * whose reasons are on hover. An ask waiting on you, or a write the backend refused, takes the second line. A copy
 * whose host row is gone shows there too; one whose row is open is a chip on that row (LiveTraderBadge). Its key off,
 * the bot places no order, not even a sell. Every write is the backend's to accept.
 */
import { useCallback, useState } from 'react';
import {
  LT_ALLOWANCE_LABEL,
  LT_ANSWERED_WHY,
  LT_APPROVE,
  LT_APPROVED,
  LT_BUSY_WHY,
  LT_ENTRY_LABEL,
  LT_EXIT_LABEL,
  LT_KEY_LABEL,
  LT_KEY_TIP_OFF,
  LT_KEY_TIP_ON,
  LT_KEY_TITLE,
  LT_RULES,
  LT_RULES_CLICK,
  LT_SKIP,
  LT_TODAY_LABEL,
  ltAfterFeesTip,
  ltBadge,
  ltBeforeFees,
  ltBotOf,
  ltFees,
  ltFeesTip,
  ltMoreAsks,
  ltOrders,
  ltSecondsLeft,
  ltSkipped,
  ltSkipsTitle,
  ltTrades,
} from '../constantGroups/live_trader';
import type { FollowedTrade } from '../followed_traders';
import { TickerLink } from '../components/TickerLink';
import { MODE_SIDES } from '../stock_read';
import { tipProps, whyProps } from '../ux';
import { prose } from './botsPageFormat';
import { answerLiveTraderAsk, patchLiveTrader } from './liveTraderApi';
import { allowancePct, copies, positionTip, ruleChips, signedUsd, skipsTip, stepsTip, usd, usd2 } from './liveTraderFormat';
import { LiveTraderRules } from './LiveTraderRules';
import { useLiveTraders } from './liveTraderStore';
import type { LiveTradersView, LtAsk, LtHost, LtPatch, LtSide } from './liveTraderTypes';
import './liveTraderStrip.css';

function Side({ label, value, onPick, disabled, why, tip, testId }: {
  label: string; value: LtSide; onPick: (side: LtSide) => void; disabled: boolean; why: string; tip: string; testId: string;
}) {
  return (
    <span className="lt-strip__side" {...tipProps(tip)}>
      <span className="lt-label">{label}</span>
      <span className="lt-seg" role="radiogroup" aria-label={label} data-testid={testId}>
        {(['you', 'nova'] as const).map(side => (
          <button key={side} type="button" role="radio" aria-checked={value === side} disabled={disabled}
            {...whyProps(disabled, why)} data-testid={`${testId}-${side}`}
            onClick={() => { if (value !== side) onPick(side); }}>
            {side === 'you' ? 'You' : 'Bot'}
          </button>
        ))}
      </span>
    </span>
  );
}

function AskLine({ ask, more, busy, onAnswer }: {
  ask: LtAsk; more: number; busy: boolean; onAnswer: (ask: LtAsk, approve: boolean) => void;
}) {
  const answered = ask.answered != null || ask.approved;
  const locked = busy || answered;
  const why = busy ? LT_BUSY_WHY : LT_ANSWERED_WHY;
  return (
    <div className="lt-strip__row lt-strip__ask" data-testid={`lt-ask-${ask.id}`}>
      <i className="lt-dot" aria-hidden="true" />
      <span className="lt-strip__ask-text" {...tipProps(prose(ask.text))}>{prose(ask.text)}</span>
      <span className="lt-muted">{answered ? LT_APPROVED : ltSecondsLeft(ask.seconds_left)}</span>
      {more > 0 ? <span className="lt-muted">{ltMoreAsks(more)}</span> : null}
      <span className="lt-strip__acts">
        <button type="button" className="lt-btn" disabled={locked} {...whyProps(locked, why)}
          data-testid={`lt-ask-skip-${ask.id}`} onClick={() => onAnswer(ask, false)}>{LT_SKIP}</button>
        <button type="button" className="lt-btn lt-btn--primary" disabled={locked} {...whyProps(locked, why)}
          data-testid={`lt-ask-approve-${ask.id}`} onClick={() => onAnswer(ask, true)}>{LT_APPROVE}</button>
      </span>
    </div>
  );
}

function StateLine({ host, open }: { host: LtHost; open: readonly FollowedTrade[] }) {
  const { name, today } = host;
  // After fees is the main number (operator 2026-10-19); a backend without the fee fields shows P/L as before.
  const feesKnown = today.net_pl_usd != null && today.fees_usd != null && today.orders != null;
  const pl = feesKnown ? today.net_pl_usd! : today.pl_usd;
  const split = `Realized ${signedUsd(today.realized_usd)} · open ${signedUsd(today.unrealized_usd)}`;
  // A copy whose host row is not open here (a key held its close, or a row from an earlier day) is said on this line.
  const loose = host.positions.filter(p => !open.some(t => copies(p, t)));
  const skips = today.skipped > 0 ? skipsTip(host.events, today.skipped) : null;
  return (
    <div className="lt-strip__row">
      <span className="lt-strip__alw">
        <span className="lt-label">{LT_ALLOWANCE_LABEL}</span>
        <span className="lt-bar"><i style={{ width: `${allowancePct(host)}%` }} /></span>
        <span className="lt-mono" data-testid={`lt-allowance-${name}`}>{usd(host.allowance.used_usd)} of {usd(host.allowance.of_usd)}</span>
      </span>
      <span className="lt-strip__today">
        <span className="lt-label">{LT_TODAY_LABEL}</span>
        <b className={`lt-mono${pl < 0 ? ' lt-down' : pl > 0 ? ' lt-up' : ''}`} data-testid={`lt-pl-${name}`}
          {...tipProps(feesKnown ? `${ltAfterFeesTip(usd2(today.fees_usd!), signedUsd(today.pl_usd))} · ${split}` : split)}>
          {signedUsd(pl)}
        </b>
        {feesKnown ? (
          <span className="lt-muted lt-mono lt-strip__gross" data-testid={`lt-gross-${name}`}>({ltBeforeFees(signedUsd(today.pl_usd))})</span>
        ) : null}
        <span className="lt-muted" data-testid={`lt-trades-${name}`} {...tipProps(stepsTip(host.events), ltBotOf(name))}>
          · {ltTrades(today.trades)} ·
        </span>
        {feesKnown ? (
          <span className="lt-muted" data-testid={`lt-fees-${name}`}
            {...tipProps(ltFeesTip(today.orders!, usd2(today.fees_usd!), today.fees_unread ?? 0), ltBotOf(name))}>
            {ltOrders(today.orders!)} · {ltFees(usd2(today.fees_usd!))}{(today.fees_unread ?? 0) > 0 ? '*' : ''} ·
          </span>
        ) : null}
        <span className={today.skipped > 0 ? 'lt-strip__skips' : 'lt-muted'} data-testid={`lt-skips-${name}`}
          {...tipProps(skips, ltSkipsTitle(name, today.skipped))}>
          {ltSkipped(today.skipped)}
        </span>
      </span>
      {loose.length ? (
        <span className="lt-strip__held">
          {loose.map(p => (
            <span key={p.id} className="lt-badge" data-testid={`lt-held-${p.id}`} {...tipProps(positionTip(p), ltBotOf(name))}>
              {ltBadge(p.qty)} <TickerLink symbol={p.symbol} look="own" className="lt-badge__ticker" />
            </span>
          ))}
        </span>
      ) : null}
    </div>
  );
}

export function LiveTraderStrip({ name, open }: { name: string; open: readonly FollowedTrade[] }) {
  const { view, apply, refresh } = useLiveTraders();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [rulesAt, setRulesAt] = useState<HTMLElement | null>(null);
  const closeRules = useCallback(() => setEditing(false), []);
  const host = view?.enabled ? view.hosts.find(h => h.name === name) ?? null : null;
  if (!view || !host) return null;
  const st = host.settings;

  async function write(run: () => Promise<LiveTradersView>) {
    setBusy(true);
    setError(null);
    try {
      apply(await run());
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      void refresh();
    } finally {
      setBusy(false);
    }
  }
  const onPatch = (who: string, body: LtPatch) => write(() => patchLiveTrader(who, body));
  const onAnswer = (ask: LtAsk, approve: boolean) => void write(() => answerLiveTraderAsk(name, ask.id, approve));
  const ask = host.asks[0] ?? null;
  const rules = [...ruleChips(st, view.sell_all_at), LT_RULES_CLICK].join('\n');

  return (
    <div className={`lt-strip${st.key ? ' is-on' : ''}`} data-testid={`lt-strip-${name}`}>
      <div className="lt-strip__row">
        <button type="button" role="switch" aria-checked={st.key} aria-label={`${name}'s ${LT_KEY_TITLE}`}
          className={`lt-key${st.key ? ' is-on' : ''}`} disabled={busy} data-testid={`lt-key-${name}`}
          {...(busy ? whyProps(true, LT_BUSY_WHY) : tipProps(st.key ? LT_KEY_TIP_ON : LT_KEY_TIP_OFF, `${name}'s ${LT_KEY_TITLE}`))}
          onClick={() => void onPatch(name, { key: !st.key })}>
          <span className="lt-label">{LT_KEY_LABEL}</span><span className="lt-key__track" aria-hidden="true" />
        </button>
        <Side label={LT_ENTRY_LABEL} value={st.entry} disabled={busy} why={LT_BUSY_WHY} tip={MODE_SIDES[st.mode]}
          testId={`lt-entry-${name}`} onPick={side => void onPatch(name, { entry: side })} />
        <Side label={LT_EXIT_LABEL} value={st.exit} disabled={busy} why={LT_BUSY_WHY} tip={MODE_SIDES[st.mode]}
          testId={`lt-exit-${name}`} onPick={side => void onPatch(name, { exit: side })} />
        <button type="button" ref={setRulesAt} className="lt-linkbtn" aria-expanded={editing} data-testid={`lt-rules-${name}`}
          {...tipProps(editing ? null : rules, ltBotOf(name))} onClick={() => setEditing(v => !v)}>
          {LT_RULES}
        </button>
      </div>
      {ask ? <AskLine ask={ask} more={host.asks.length - 1} busy={busy} onAnswer={onAnswer} />
        : error ? <p className="lt-strip__error" role="alert" data-testid={`lt-error-${name}`} {...tipProps(prose(error))}>{prose(error)}</p>
          : <StateLine host={host} open={open} />}
      {editing && rulesAt ? (
        <LiveTraderRules anchor={rulesAt} host={host} sellAllAt={view.sell_all_at} busy={busy} onPatch={onPatch}
          onClose={closeRules} />
      ) : null}
    </div>
  );
}
