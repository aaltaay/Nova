/**
 * Top stocks by sector (ADR 053): the biggest names or the small-cap runners, for the period chosen. Every sector has
 * a card with its five heaviest holdings (Movers retired 2026-10-14: its cards often held one stock); a row, its
 * symbol and the card's ETF open the Trader.
 */
import { MARKET_TOP_KINDS, TOP_KIND_LABEL } from './constants';
import { price, signedPct, tone } from './format';
import { PeriodSwitch, Spark, Sym } from './parts';
import type { BlockPeriods, TopCard, TopKind, TopStocks } from './types';

const HINT: Record<TopKind, string> = {
  biggest: "each sector's five heaviest holdings (State Street's daily file), priced by IBKR",
  runners: "Nova's small-cap runners, grouped by IBKR industry",
};

function Card({ card, onOpen }: { card: TopCard; onOpen?: (symbol: string) => void }) {
  return (
    <div className="mk-top__card" data-testid={`market-top-card-${card.etf ?? card.name}`}>
      <div className="mk-top__head">
        <span>{card.name} {card.etf ? <Sym symbol={card.etf} onOpen={onOpen} muted /> : null}</span>
        {card.change_pct != null ? <span className={`is-${tone(card.change_pct)}`}>{signedPct(card.change_pct)}</span> : null}
      </div>
      {card.rows.length === 0 ? <p className="mk-small mk-muted mk-top__none">no price yet</p> : null}
      {card.rows.map((r) => (
        <div key={r.symbol} className={`mk-top__row${onOpen ? ' is-link' : ''}`}
          onClick={onOpen ? () => onOpen(r.symbol) : undefined}>
          <Sym symbol={r.symbol} onOpen={onOpen} />
          {r.spark ? <Spark points={r.spark} height={16} label={`${r.symbol} closes`} /> : <span />}
          <span className={`mk-r mk-b is-${tone(r.change_pct)}`}>{signedPct(r.change_pct, 1)}</span>
          <span className="mk-r mk-muted mk-small">{price(r.last)}</span>
        </div>
      ))}
    </div>
  );
}

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
      {top.why ? <p className="mk-wait" role="status">{top.why}</p> : null}
      <div className="mk-top__grid">
        {top.cards.map((card) => <Card key={card.name} card={card} onOpen={onOpen} />)}
      </div>
    </section>
  );
}
