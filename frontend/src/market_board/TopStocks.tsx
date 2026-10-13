/** Top stocks by sector (ADR 053): movers, the biggest names or the small-cap runners, for the period chosen. */
import { MARKET_TOP_KINDS, TOP_KIND_LABEL } from './constants';
import { price, signedPct, tone } from './format';
import { PeriodSwitch, Spark, Sym } from './parts';
import type { BlockPeriods, TopKind, TopStocks } from './types';

const HINT: Record<TopKind, string> = {
  movers: 'IBKR large-cap gainers by sector (7 D / 30 D: the best of each sector\'s biggest names)',
  biggest: "each sector's heaviest holdings (State Street's daily file)",
  runners: "Nova's small-cap runners, grouped by IBKR industry",
};

export function TopStocksCard({ top, onChange, onOpen }: {
  top: TopStocks;
  onChange: (next: BlockPeriods['top']) => void;
  onOpen?: (symbol: string) => void;
}) {
  return (
    <section className="mk-card mk-top" data-testid="market-top">
      <header className="mk-card__head">
        <h3>Top stocks by sector</h3>
        <span className="mk-seg" role="radiogroup" aria-label="Top stocks list">
          {MARKET_TOP_KINDS.map((k) => (
            <button key={k} type="button" role="radio" aria-checked={k === top.kind} className={k === top.kind ? 'is-on' : ''}
              onClick={() => onChange({ kind: k, period: top.period })}>
              {TOP_KIND_LABEL[k]}
            </button>
          ))}
        </span>
        <PeriodSwitch value={top.period} onChange={(p) => onChange({ kind: top.kind, period: p })} label="Top stocks period" />
        <span className="mk-hint">{HINT[top.kind]} · click a stock to open it in the Trader</span>
      </header>
      {top.why && top.cards.length === 0 ? <p className="mk-wait" role="status">{top.why}</p> : null}
      <div className="mk-top__grid">
        {top.cards.map((card) => (
          <div key={card.name} className="mk-top__card">
            <div className="mk-top__head">
              <span>{card.name} {card.etf ? <span className="mk-muted mk-small">{card.etf}</span> : null}</span>
              {card.change_pct != null ? <span className={`is-${tone(card.change_pct)}`}>{signedPct(card.change_pct)}</span> : null}
            </div>
            {card.rows.length === 0 ? <p className="mk-small mk-muted">none in the scan</p> : null}
            {card.rows.map((r) => (
              <div key={r.symbol} className="mk-top__row">
                <Sym symbol={r.symbol} onOpen={onOpen} />
                {r.spark ? <Spark points={r.spark} height={16} label={`${r.symbol} closes`} /> : <span />}
                <span className={`mk-r mk-b is-${tone(r.change_pct)}`}>{signedPct(r.change_pct, 1)}</span>
                <span className="mk-r mk-muted mk-small">{price(r.last)}</span>
              </div>
            ))}
          </div>
        ))}
      </div>
    </section>
  );
}
