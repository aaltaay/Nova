/**
 * The Market page (ADR 053; operator ask 2026-10-12, mockups v1-v5 approved): the day's market health at a
 * glance -- the day read, futures and macro, the sector and industry boards, NYSE breadth, the small-cap climate
 * and the top stocks by sector. Read-only: nothing here places an order; a stock symbol opens the Trader. Each
 * block that looks back has its own 1 D / 7 D / 30 D switch, remembered on the desk (periods.ts).
 */
import { useSampleRoute } from '../sample_data/useSampleRoute';
import { BreadthCard } from './BreadthCard';
import { ClimateCard } from './ClimateCard';
import { MARKET_OFF, MARKET_OLD_API, MARKET_REPLAY_NOTE, MARKET_TITLE } from './constants';
import { DayReadCard } from './DayRead';
import { until } from './format';
import { useBlockPeriods } from './periods';
import { SectorBoardCard } from './SectorBoard';
import { QuoteTiles } from './Tiles';
import { TopStocksCard } from './TopStocks';
import type { MarketBoard, Session, SourceStatus } from './types';
import { useMarketBoard } from './useMarketBoard';
import './market.css';

export interface MarketPageProps {
  onOpenTrader?: (symbol: string) => void;
}

const PHASE_PILL: Record<Session['phase'], string> = {
  premarket: 'Premarket',
  regular: 'Open',
  after_hours: 'After hours',
  closed: 'Closed',
};

function sessionWords(s: Session, now: number): string {
  const day = new Date(`${s.date}T12:00:00Z`).toLocaleDateString('en-US', {
    weekday: 'long', month: 'long', day: 'numeric', timeZone: 'UTC',
  });
  const next = s.next ? until(s.next.at - now) : null;
  const phase = s.phase === 'premarket' ? `premarket · the open in ${next}`
    : s.phase === 'regular' ? `regular session · ${next} to the close`
      : s.phase === 'after_hours' ? `after hours · ends in ${next}`
        : 'markets closed';
  return `${day} · ${phase}${s.holiday ? ` · ${s.holiday}` : ''}`;
}

function Sources({ sources }: { sources: SourceStatus[] }) {
  return (
    <span className="mk-sources" aria-label="Sources">
      {sources.map((s) => (
        <span key={s.id} className={`mk-sources__dot is-${s.ok == null ? 'idle' : s.ok ? 'ok' : 'bad'}`}
          title={`${s.label}: ${s.ok == null ? 'not asked yet' : s.ok ? 'answering' : s.error ?? 'failing'}`}>
          {s.label}
        </span>
      ))}
    </span>
  );
}

function Head({ board }: { board: MarketBoard | null }) {
  return (
    <div className="mk-head">
      <h2>{MARKET_TITLE}</h2>
      {board ? (
        <>
          <span className="mk-head__sub">{sessionWords(board.session, board.generated_at)}</span>
          <span className={`mk-pill is-${board.session.phase}`}>{PHASE_PILL[board.session.phase]}</span>
          {board.replay_desk ? <span className="mk-pill">{MARKET_REPLAY_NOTE}</span> : null}
          <Sources sources={board.sources} />
        </>
      ) : null}
    </div>
  );
}

export function MarketPage({ onOpenTrader }: MarketPageProps) {
  const sample = useSampleRoute();
  const [periods, setPeriods] = useBlockPeriods(!sample);
  const { data: board, error, unavailable } = useMarketBoard(periods);

  if (unavailable || !board || !board.enabled) {
    const words = unavailable ? MARKET_OLD_API : board && !board.enabled ? MARKET_OFF : error ?? 'Reading the market …';
    return (
      <div className="mk-page" data-testid="market-page">
        <Head board={null} />
        <p className="mk-wait" role="status">{words}</p>
      </div>
    );
  }

  return (
    <div className="mk-page" data-testid="market-page">
      <Head board={board} />
      {error ? <p className="mk-stale" role="status">{error} -- showing the last good answer.</p> : null}
      <div className="mk-row1">
        <DayReadCard read={board.day_read} events={board.events} now={board.generated_at} />
        <QuoteTiles quotes={board.quotes} session={board.session} />
      </div>
      <div className="mk-row2">
        <SectorBoardCard kind="sectors" board={board.sectors} onOpen={onOpenTrader}
          onPeriod={(p) => setPeriods({ ...periods, sectors: p })} />
        <SectorBoardCard kind="industries" board={board.industries} onOpen={onOpenTrader}
          onPeriod={(p) => setPeriods({ ...periods, industries: p })} />
        <div className="mk-right">
          <BreadthCard breadth={board.breadth} />
          <ClimateCard c={board.climate} onOpen={onOpenTrader} onPeriod={(p) => setPeriods({ ...periods, climate: p })} />
        </div>
      </div>
      <TopStocksCard top={board.top} onOpen={onOpenTrader} onChange={(t) => setPeriods({ ...periods, top: t })} />
    </div>
  );
}
