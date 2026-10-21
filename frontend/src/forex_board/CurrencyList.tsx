/**
 * "By currency" on the Forex page (ADR 061, mockup v2): every currency biggest first, with how much of it trades a day
 * (the BIS survey's), its strength (and its move against the dollar) and its futures pressure as bars from a centre
 * line, and ≠ where the two disagree. A currency IBKR does not price says "no price", one without a future "no
 * futures". The rows share the list's height (the page never scrolls); a short list drops their second lines.
 */
import { signedPct, tone, usd } from '../world_board/format';
import { FUTURES_BAR_SCALE_PCT, STRENGTH_BAR_SCALE_PCT } from './constants';
import type { Currency, Period } from './types';

interface Props {
  currencies: Currency[];
  period: Period;
  hovered: string | null;
  onHover: (code: string | null) => void;
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

function quoteWord(c: Currency, priced: number): string {
  if (c.code === 'USD') return `vs the other ${priced - 1}`;
  return c.price.pair && c.price.vs_usd_pct != null ? c.price.pair : c.price.error ? 'no IBKR price' : c.price.pair ?? '';
}

function strengthNote(c: Currency): string {
  if (c.strength_pct == null) return 'no price';
  if (c.code === 'USD') return 'vs basket';
  if (c.price.basis === 'future') return 'from futures';
  return `${signedPct(c.price.vs_usd_pct, 2)} vs USD`;
}

function futuresNote(c: Currency, futures: number): string {
  const f = c.futures;
  if (f.pressure_usd == null) return f.refused.length ? 'no feed' : f.basis === null && f.error === 'no CME future' ? 'no futures' : 'waiting';
  const code = c.code === 'USD' ? `all ${futures}` : (f.instrument?.label.match(/\(([^)]+)\)$/)?.[1] ?? f.instrument?.symbol ?? '');
  return `${signedPct(f.pressure_pct)} · ${code}`;
}

export function CurrencyList({ currencies, period, hovered, onHover }: Props) {
  const priced = currencies.filter((c) => c.strength_pct != null).length;
  const futures = currencies.filter((c) => c.code !== 'USD' && c.futures.pressure_usd != null).length;
  return (
    <div className="gb-list fx-list" data-testid="forex-list" role="table" aria-label="Currencies, biggest first">
      <div className="gb-list__head" role="row">
        <span role="columnheader">Currency</span>
        <span role="columnheader" className="gb-c">A day</span>
        <span role="columnheader" className="gb-c">Strength</span>
        <span role="columnheader" className="gb-c">Futures</span>
      </div>
      {currencies.map((c) => (
        <div key={c.code} role="row" data-testid={`forex-row-${c.code}`}
          className={`gb-row${hovered === c.code ? ' is-hovered' : ''}${c.strength_pct == null ? ' is-muted' : ''}`}
          onMouseEnter={() => onHover(c.code)} onMouseLeave={() => onHover(null)}>
          <div className="gb-row__name" role="cell">
            <span className="gb-row__line">
              <i className={`gb-dot is-${c.home.open ? 'open' : 'closed'}`}
                title={c.home.open ? `its home session (${c.city}) is open` : `its home session (${c.city}) is closed`} />
              <b>{c.code}</b>
            </span>
            <small>{c.name} · {quoteWord(c, priced)}</small>
          </div>
          <div className="fx-size-cell" role="cell" title={`${c.size.pair} is its biggest pair: ${usd(c.size.pair_usd)} a day`}>
            <b>{usd(c.size.usd)}</b>
            <small>{Math.round(c.size.share_pct)}% of trades</small>
          </div>
          <div className="gb-row__pair" role="cell">
            <Bar value={c.strength_pct} scale={STRENGTH_BAR_SCALE_PCT[period]} />
            <span className={`gb-num is-${tone(c.strength_pct)}`}>
              {signedPct(c.strength_pct, 2)}
              <small>{strengthNote(c)}</small>
            </span>
          </div>
          <div className="gb-row__pair" role="cell">
            <Bar value={c.futures.pressure_pct} scale={FUTURES_BAR_SCALE_PCT} />
            <span className={`gb-num is-${tone(c.futures.pressure_usd)}`}>
              {usd(c.futures.pressure_usd, true)}
              <small>{futuresNote(c, futures)}</small>
            </span>
          </div>
          <span className="gb-row__flag" role="cell" title={c.mixed ? 'futures pressure and strength disagree' : undefined}>
            {c.mixed ? '≠' : ''}
          </span>
        </div>
      ))}
    </div>
  );
}
