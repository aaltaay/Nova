/**
 * "By exchange" on the Global page (ADR 060): every market ranked by its pressure, with its pressure and its index
 * move side by side as bars from a centre line, and ≠ where the two disagree. A country ETF's symbol opens the
 * Trader; a market IBKR refused says "no feed". The rows share the list's height (the page never scrolls); a short
 * list drops each row's second line, never the "via" flag on its first. Each exchange's size sits beside its name on
 * the first line ("NYSE $29.5T + Nasdaq $38.5T").
 */
import { Fragment, type ReactNode } from 'react';
import { MOVE_BAR_SCALE_PCT, PRESSURE_BAR_SCALE_PCT, STATE_WORD } from './constants';
import { monthWord, signedPct, sizeUsd, tone, usd } from './format';
import type { Market, Period } from './types';

interface Props {
  markets: Market[];
  period: Period;
  hovered: string | null;
  onHover: (id: string | null) => void;
  onOpenTrader?: (symbol: string) => void;
}

function Bar({ value, scale }: { value: number | null; scale: number }) {
  const width = value == null ? 0 : Math.min(1, Math.abs(value) / scale) * 50;
  return (
    <div className="gb-bar" aria-hidden>
      <div className="gb-bar__mid" />
      {value != null && value !== 0 ? (
        <div className={`gb-bar__fill is-${tone(value)}`}
          style={value > 0 ? { left: '50%', width: `${width}%` } : { right: '50%', width: `${width}%` }} />
      ) : null}
    </div>
  );
}

/** Pressure first; markets with no pressure yet last, in the board's order. */
export function ranked(markets: Market[]): Market[] {
  const key = (m: Market) => m.flow.pressure_usd ?? (m.flow.pressure_pct != null ? m.flow.pressure_pct * 1e6 : null);
  return [...markets].sort((a, b) => {
    const ka = key(a);
    const kb = key(b);
    if (ka == null && kb == null) return 0;
    if (ka == null) return 1;
    if (kb == null) return -1;
    return kb - ka;
  });
}

/**
 * Each exchange the market's label names, beside its own published size: "NYSE + Nasdaq" pairs with the size's two
 * parts in order; a label naming one exchange takes the whole. A label whose pieces do not match the parts keeps one
 * total; no published size, no number.
 */
export function sizedExchanges(m: Market): { name: string; usd: number | null }[] {
  const names = m.exchange.split(' + ');
  const size = m.size;
  if (!size) return names.map((name) => ({ name, usd: null }));
  if (names.length > 1 && names.length === size.parts.length) {
    return names.map((name, i) => ({ name, usd: size.parts[i].usd }));
  }
  return [{ name: m.exchange, usd: size.usd }];
}

/** What the row reads when it is not its home future: its US-listed ETF (opens the Trader), "no feed" or "waiting". */
function flag(m: Market, onOpenTrader?: (symbol: string) => void): ReactNode {
  const inst = m.flow.instrument;
  if (!inst || !m.flow.basis) {
    return m.flow.refused.length ? <span className="gb-nofeed">no feed</span> : <span className="gb-muted">waiting</span>;
  }
  if (m.flow.basis !== 'etf') return null;
  return (
    <span className="gb-via is-etf">
      via{' '}
      {onOpenTrader ? (
        <button type="button" className="gb-link" onClick={() => onOpenTrader(inst.symbol)}
          title={`Open ${inst.symbol} in the Trader`}>{inst.symbol}</button>
      ) : inst.symbol}
    </span>
  );
}

export function ExchangeList({ markets, period, hovered, onHover, onOpenTrader }: Props) {
  return (
    <div className="gb-list" data-testid="global-list" role="table" aria-label="Markets by pressure">
      <div className="gb-list__head" role="row">
        <span role="columnheader">Market</span>
        <span role="columnheader" className="gb-c">Pressure</span>
        <span role="columnheader" className="gb-c">Index move</span>
      </div>
      {ranked(markets).map((m) => (
        <div key={m.id} role="row" data-testid={`global-row-${m.id}`}
          className={`gb-row${hovered === m.id ? ' is-hovered' : ''}`}
          onMouseEnter={() => onHover(m.id)} onMouseLeave={() => onHover(null)}>
          <div className="gb-row__name" role="cell">
            <span className="gb-row__line">
              <i className={`gb-dot is-${m.session.state}`} title={STATE_WORD[m.session.state]} />
              <b className="gb-row__ex" data-testid={`global-exchange-${m.id}`}
                title={m.size ? `Market size ≈ ${sizeUsd(m.size.usd)}, ${monthWord(m.size.as_of)}, ${m.size.source}` : undefined}>
                {sizedExchanges(m).map((e, i) => (
                  <Fragment key={e.name}>
                    {i ? ' + ' : ''}{e.name}
                    {e.usd != null ? <span className="gb-size"> {sizeUsd(e.usd)}</span> : null}
                  </Fragment>
                ))}
              </b>
              {flag(m, onOpenTrader)}
            </span>
            <small>
              {m.name}{m.flow.basis === 'future' && m.flow.instrument ? ` · ${m.flow.instrument.label}` : ''}
            </small>
          </div>
          <div className="gb-row__pair" role="cell">
            <Bar value={m.flow.pressure_pct} scale={PRESSURE_BAR_SCALE_PCT} />
            <span className={`gb-num is-${tone(m.flow.pressure_pct)}`}>
              {m.flow.pressure_usd != null ? usd(m.flow.pressure_usd, true) : signedPct(m.flow.pressure_pct)}
              <small>{m.flow.pressure_usd != null ? signedPct(m.flow.pressure_pct) : m.flow.pressure_pct != null ? 'no $ yet' : ''}</small>
            </span>
          </div>
          <div className="gb-row__pair" role="cell">
            <Bar value={m.move.pct} scale={MOVE_BAR_SCALE_PCT[period]} />
            <span className={`gb-num is-${tone(m.move.pct)}`}>
              {signedPct(m.move.pct, 2)}
              <small>{m.move.basis === 'index' ? m.move.instrument?.label : m.move.basis ? `${m.move.instrument?.symbol}` : ''}</small>
            </span>
          </div>
          <span className="gb-row__flag" role="cell" title={m.mixed ? 'pressure and index move disagree' : undefined}>
            {m.mixed ? '≠' : ''}
          </span>
        </div>
      ))}
    </div>
  );
}
