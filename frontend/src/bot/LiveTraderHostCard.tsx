/**
 * One TraderTV host's bot on Bots > LiveTrader Bots (ADR 055, mockup v1 approved 2026-10-14): its key, who enters
 * and who exits (the stock's own Entry / Exit switch and words, ADR 037), what it asks you, what it may spend and has
 * spent, what it holds, and its newest steps and skips with their reasons. Its key off, the bot places no order, not
 * even a sell: nothing is sold when it turns off, so there is nothing to ask (operator decision 2026-10-15). Every
 * write is the backend's to accept.
 */
import { useState } from 'react';
import {
  LT_ALLOWANCE_LABEL,
  LT_ANSWERED_WHY,
  LT_APPROVE,
  LT_BUSY_WHY,
  LT_CHANGE,
  LT_DONE,
  LT_ENTRY_LABEL,
  LT_EVENTS_SHOWN,
  LT_EXIT_LABEL,
  LT_KEY_LABEL,
  LT_KEY_TIP_OFF,
  LT_KEY_TIP_ON,
  LT_NO_POSITIONS,
  LT_SKIP,
  LT_SKIPPED_LABEL,
  LT_TODAY_LABEL,
  LT_TRADES_LABEL,
} from '../constantGroups/live_trader';
import { MODE_SIDES } from '../stock_read';
import { tipProps, whyProps } from '../ux';
import { etClock, prose } from './botsPageFormat';
import { allowancePct, px, ruleChips, signedUsd, sparkPoints, usd } from './liveTraderFormat';
import { LiveTraderSettings } from './LiveTraderSettings';
import type { LtAsk, LtHost, LtPatch, LtSide } from './liveTraderTypes';
import { TickerLink } from '../components/TickerLink';

interface Props {
  host: LtHost;
  sellAllAt: string;
  busy: boolean;
  onPatch: (name: string, body: LtPatch) => Promise<void>;
  onAnswer: (name: string, ask: LtAsk, approve: boolean) => Promise<void>;
}

function Side({ label, value, onPick, disabled, why, testId }: {
  label: string; value: LtSide; onPick: (side: LtSide) => void; disabled: boolean; why: string; testId: string;
}) {
  return (
    <span className="lt-who__side">
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

function Spark({ series }: { series: LtHost['today']['series'] }) {
  const got = sparkPoints(series, 150, 30);
  if (!got) return null;
  const last = series.length ? series[series.length - 1][1] : 0;
  return (
    <svg className="lt-spark" width="150" height="30" viewBox="0 0 150 30" aria-hidden="true">
      <line x1="0" y1={got.zeroY} x2="150" y2={got.zeroY} className="lt-spark__zero" />
      <polyline points={got.points} className={`lt-spark__line${last < 0 ? ' is-down' : ''}`} />
    </svg>
  );
}

export function LiveTraderHostCard({ host, sellAllAt, busy, onPatch, onAnswer }: Props) {
  const [editing, setEditing] = useState(false);
  const st = host.settings;
  const name = host.name;

  async function onKey() {
    await onPatch(name, { key: !st.key });
  }

  return (
    <article className={`lt-host${st.key ? ' is-on' : ''}`} data-testid={`lt-host-${name}`}>
      <div className="lt-host__head">
        {host.face
          ? <img className="lt-av" src={host.face} alt="" />
          : <span className="lt-av" aria-hidden="true">{name.slice(0, 1)}</span>}
        <div className="lt-host__id">
          <b className="lt-host__name">{name}</b>
          <span className={`lt-host__state is-${host.state.tone}`} data-testid={`lt-state-${name}`}>
            <i className="lt-dot" aria-hidden="true" />{host.state.text}
          </span>
        </div>
        <button type="button" role="switch" aria-checked={st.key} className={`lt-key${st.key ? ' is-on' : ''}`}
          disabled={busy} {...whyProps(busy, LT_BUSY_WHY)} data-testid={`lt-key-${name}`}
          {...tipProps(st.key ? LT_KEY_TIP_ON : LT_KEY_TIP_OFF, LT_KEY_LABEL)}
          onClick={() => void onKey()}>
          <span className="lt-label">{LT_KEY_LABEL}</span><span className="lt-key__track" aria-hidden="true" />
        </button>
      </div>

      <div className="lt-who">
        <Side label={LT_ENTRY_LABEL} value={st.entry} disabled={busy} why={LT_BUSY_WHY} testId={`lt-entry-${name}`}
          onPick={side => void onPatch(name, { entry: side })} />
        <Side label={LT_EXIT_LABEL} value={st.exit} disabled={busy} why={LT_BUSY_WHY} testId={`lt-exit-${name}`}
          onPick={side => void onPatch(name, { exit: side })} />
        <span className="lt-who__mode" data-testid={`lt-mode-${name}`}>{MODE_SIDES[st.mode]}</span>
      </div>

      {host.asks.map(ask => {
        const answered = ask.answered != null || ask.approved;
        const locked = busy || answered;
        const why = busy ? LT_BUSY_WHY : LT_ANSWERED_WHY;
        return (
          <div key={ask.id} className="lt-ask" data-testid={`lt-ask-${ask.id}`}>
            <span className="lt-ask__text">{prose(ask.text)}</span>
            <span className="lt-ask__left">{ask.answered === true || ask.approved ? 'approved' : `${ask.seconds_left} s left`}</span>
            <span className="lt-ask__acts">
              <button type="button" className="lt-btn" disabled={locked} {...whyProps(locked, why)}
                data-testid={`lt-ask-skip-${ask.id}`} onClick={() => void onAnswer(name, ask, false)}>{LT_SKIP}</button>
              <button type="button" className="lt-btn lt-btn--primary" disabled={locked} {...whyProps(locked, why)}
                data-testid={`lt-ask-approve-${ask.id}`} onClick={() => void onAnswer(name, ask, true)}>{LT_APPROVE}</button>
            </span>
          </div>
        );
      })}

      <div className="lt-alw">
        <span className="lt-label">{LT_ALLOWANCE_LABEL}</span>
        <span className="lt-bar"><i style={{ width: `${allowancePct(host)}%` }} /></span>
        <span className="lt-mono" data-testid={`lt-allowance-${name}`}>{usd(host.allowance.used_usd)} of {usd(host.allowance.of_usd)}</span>
      </div>

      <div className="lt-kpis">
        <span className="lt-kpi"><b className={`lt-mono ${host.today.pl_usd < 0 ? 'is-down' : host.today.pl_usd > 0 ? 'is-up' : ''}`}
          data-testid={`lt-pl-${name}`}>{signedUsd(host.today.pl_usd)}</b><small>{LT_TODAY_LABEL}</small></span>
        <span className="lt-kpi"><b className="lt-mono">{host.today.trades}</b><small>{LT_TRADES_LABEL}</small></span>
        <span className="lt-kpi"><b className="lt-mono">{host.today.skipped}</b><small>{LT_SKIPPED_LABEL}</small></span>
        <Spark series={host.today.series} />
      </div>

      {host.positions.length ? (
        <table className="lt-pos" data-testid={`lt-positions-${name}`}>
          <thead><tr><th>Stock</th><th>Side</th><th>Shares</th><th>Bot in</th><th>Their avg</th><th>Now</th><th>P/L</th></tr></thead>
          <tbody>
            {host.positions.map(p => (
              <tr key={p.id} title={p.note ?? undefined}>
                <td className="lt-pos__sym"><TickerLink symbol={p.symbol} /></td>
                <td><span className={`lt-tag lt-tag--${p.side}`}>{p.side === 'short' ? 'SHORT' : 'LONG'}</span></td>
                <td className="lt-mono">{p.qty}</td>
                <td className="lt-mono">{px(p.avg_cost)}</td>
                <td className="lt-mono">{px(p.their_avg)}{p.adds_followed ? ` · +${p.adds_followed} add${p.adds_followed === 1 ? '' : 's'}` : ''}</td>
                <td className="lt-mono">{px(p.now)}</td>
                <td className={`lt-mono ${(p.pl_usd ?? 0) < 0 ? 'is-down' : (p.pl_usd ?? 0) > 0 ? 'is-up' : ''}`}>{signedUsd(p.pl_usd)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : <p className="lt-muted">{LT_NO_POSITIONS}</p>}

      {host.events.length ? (
        <ul className="lt-events" data-testid={`lt-events-${name}`}>
          {host.events.slice(0, LT_EVENTS_SHOWN).map((e, i) => (
            <li key={`${e.ts}-${i}`}>
              <span className="lt-events__t lt-mono">{e.ts ? etClock(e.ts) : ''}</span>
              <i className={`lt-events__dot is-${e.tone}`} aria-hidden="true" />
              <span className="lt-events__text">{prose(e.text ?? '')}</span>
            </li>
          ))}
        </ul>
      ) : null}

      <div className="lt-rules">
        {ruleChips(st, sellAllAt).map(chip => <span key={chip} className="lt-chip">{chip}</span>)}
        <button type="button" className="lt-linkbtn lt-rules__edit" data-testid={`lt-change-${name}`}
          onClick={() => setEditing(v => !v)}>{editing ? LT_DONE : LT_CHANGE}</button>
      </div>
      {editing ? <LiveTraderSettings name={name} settings={st} busy={busy} onPatch={onPatch} /> : null}
    </article>
  );
}
