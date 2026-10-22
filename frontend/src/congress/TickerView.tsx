/**
 * A stock's page (ADR 066): every member who reported trading it -- who bought, who sold, each trade as filed -- and
 * the stock itself one click away in the Trader (IBKR's chart).
 */
import { TickerLink } from '../components/TickerLink';
import { useCongressTicker } from './api';
import { FaceStack } from './Face';
import { TradeTable } from './TradeTable';
import type { Member } from './types';

export function TickerView({ ticker, year, onBack, onOpenMember, onOpenTrader }: {
  ticker: string;
  year: number;
  onBack: () => void;
  onOpenMember: (bioguide: string) => void;
  onOpenTrader: (symbol: string) => void;
}) {
  const { data, error } = useCongressTicker(ticker);
  const back = <button type="button" className="cg-back" onClick={onBack} data-testid="congress-back">‹ Congress</button>;
  if (!data) return <div className="cg-view">{back}<p className="cg-muted" role="status">{error ?? `Reading ${ticker} …`}</p></div>;
  const byBio = new Map<string, Member>();
  data.trades.forEach((t) => {
    if (t.member) byBio.set(t.member.bioguide, t.member);
  });
  const faces = (bios: string[]) => bios.map((b) => byBio.get(b) ?? null);
  return (
    <div className="cg-view" data-testid="congress-ticker">
      {back}
      <section className="cg-card cg-member">
        <div className="cg-member__head">
          <span className="cg-tile cg-tile--big"><TickerLink symbol={ticker} onOpen={onOpenTrader} look="own" /></span>
          <div className="cg-member__who">
            <h2><TickerLink symbol={ticker} onOpen={onOpenTrader} look="own" /></h2>
            <div className="cg-muted">{data.asset ?? 'No asset name in the reports'}</div>
            <div className="cg-tk-who">
              <span><b className="is-up">{data.buyers.length}</b> bought <FaceStack members={faces(data.buyers)} ring="#30d158" n={8} /></span>
              <span><b className="is-down">{data.sellers.length}</b> sold <FaceStack members={faces(data.sellers)} ring="#ff453a" n={8} /></span>
            </div>
          </div>
          <button type="button" className="cg-follow" onClick={() => onOpenTrader(ticker)} data-testid="congress-open-trader">
            Open in Trader
          </button>
        </div>
      </section>
      <section className="cg-card">
        <div className="cg-card__head"><h3 className="cg-card__title">Every report of <TickerLink symbol={ticker} onOpen={onOpenTrader} look="own" /></h3>
          <span className="cg-card__source">{data.trades.length} trades · newest report first</span></div>
        <TradeTable trades={data.trades} year={year} withMember onOpenMember={onOpenMember} onOpenTrader={onOpenTrader} />
      </section>
    </div>
  );
}
