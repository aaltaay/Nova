/**
 * One market's hover card on the Global page (ADR 060): its session on its own clock, its pressure and index move
 * with where each came from, and anything IBKR refused for it. Shared by the map and the list.
 */
import { BASIS_WORD, MIXED_DEF, STATE_WORD } from './constants';
import { etWhen, firstSentence, localTime, monthWord, signedPct, sizeUsd, tone, until, usd } from './format';
import type { Market } from './types';

function via(m: Market): string {
  const inst = m.flow.instrument;
  if (!inst || !m.flow.basis) return m.flow.error ?? 'no read yet';
  const where = inst.kind === 'future' && inst.contract ? `${inst.label} (${inst.contract}, ${inst.exchange})` : inst.label;
  return m.flow.basis === 'etf' ? `${where} -- US money in US hours` : where;
}

/** Where the move came from; an ETF's label already says it is one ("EWC (US-listed ETF)"). */
function moveSource(m: Market): string {
  const label = m.move.instrument?.label ?? '';
  return m.move.basis === 'etf' || !m.move.basis ? label : `${label} (${BASIS_WORD[m.move.basis]})`;
}

export function MarketTip({ m, now }: { m: Market; now: number }) {
  const s = m.session;
  const when = s.state === 'open' ? `open, closes ${until(s.close_at, now)}`
    : s.state === 'break' ? 'lunch break'
      : s.next_open_at ? `${STATE_WORD[s.state]}, opens ${until(s.next_open_at, now)}` : STATE_WORD[s.state];
  return (
    <div className="gb-tip" role="tooltip" data-testid={`global-tip-${m.id}`}>
      <div className="gb-tip__head">
        <b>{m.exchange}</b>
        <span>{m.name} · {m.city} · {localTime(now, m.tz)} local · {when}</span>
      </div>
      <div className="gb-tip__row">
        <span>Pressure</span>
        <b className={`is-${tone(m.flow.pressure_usd ?? m.flow.pressure_pct)}`}>
          {m.flow.pressure_usd != null ? `${usd(m.flow.pressure_usd, true)} · ` : ''}{signedPct(m.flow.pressure_pct)}
        </b>
      </div>
      <div className="gb-tip__row">
        <span>Money traded</span>
        <b>{usd(m.flow.traded_usd)}</b>
      </div>
      <div className="gb-tip__row">
        <span>Index move</span>
        <b className={`is-${tone(m.move.pct)}`}>{signedPct(m.move.pct, 2)}</b>
      </div>
      <div className="gb-tip__row" data-testid={`global-tip-size-${m.id}`}>
        <span>Market size</span>
        <b>{m.size ? `≈ ${sizeUsd(m.size.usd)}` : '--'}</b>
      </div>
      <div className="gb-tip__src">
        Money: {via(m)}
        {m.flow.fx ? ` · ${m.flow.fx.currency} at $${m.flow.fx.usd_per_unit.toPrecision(4)} (IBKR, ${m.flow.fx.date ?? 'last close'})` : ''}
      </div>
      <div className="gb-tip__src">
        Move: {m.move.basis ? moveSource(m) : m.move.error ?? 'no read yet'}
        {m.move.data_type && m.move.data_type !== 'live' ? ` · ${m.move.data_type}` : ''}
      </div>
      {m.size ? (
        <div className="gb-tip__src">
          Size: {m.size.parts.length > 1 ? `${m.size.parts.map((p) => `${p.name} ${sizeUsd(p.usd)}`).join(' + ')} · ` : ''}
          {monthWord(m.size.as_of)}, {m.size.source} -- published monthly, not live
        </div>
      ) : null}
      {m.flow.last_bar_at ? <div className="gb-tip__src">Last trade read: {etWhen(m.flow.last_bar_at, now)} ET</div> : null}
      {m.flow.error && m.flow.basis ? <div className="gb-tip__warn">{m.flow.error}</div> : null}
      {m.flow.refused.map((r) => (
        <div key={`${r.instrument}`} className="gb-tip__warn" title={r.error ?? undefined}>No feed for {r.instrument}: {firstSentence(r.error ?? '')}</div>
      ))}
      {s.calendar === 'clock' ? <div className="gb-tip__src">Local holidays are not in Nova's calendar.</div> : null}
      {m.mixed ? <div className="gb-tip__mixed">≠ {MIXED_DEF}</div> : null}
    </div>
  );
}
