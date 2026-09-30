/**
 * The Cryptos page (ADR 040; operator ask 2026-09-30, the approved mockup built as it was drawn): what a trader
 * needs from the 24/7 crypto market -- the tiles, the coins, a chart, the clock, the stocks crypto moves, leverage,
 * money flows, what comes next and the day's news -- and a hover card that explains every number. Read-only:
 * nothing here places an order; a stock symbol opens the Trader.
 */
import { useState } from 'react';
import { BridgeCard } from './BridgeCard';
import { ChartCard } from './ChartCard';
import { ClockCard } from './ClockCard';
import { CoinsCard } from './CoinsCard';
import {
  CHART_DEFAULT,
  CRYPTOS_OFF,
  CRYPTOS_OLD_API,
  CRYPTOS_REPLAY_NOTE,
  CRYPTOS_SUB,
  CRYPTOS_TITLE,
} from './constants';
import { countdown } from './format';
import { KpiStrip } from './KpiStrip';
import { FlowsCard, LeverageCard, NextNewsCard } from './LowerCards';
import { tipCryptoOpen, tipStocksStatus } from './tips/glossaryDesk';
import { TipHost, useTip } from './tips/TipHost';
import type { CandleTf, CryptoBoard } from './types';
import { useCryptoBoard } from './useCryptoData';
import './cryptos.css';

export interface CryptosPageProps {
  onOpenTrader: (symbol: string) => void;
}

export function CryptosPage({ onOpenTrader }: CryptosPageProps) {
  return (
    <TipHost>
      <CryptosBody onOpenTrader={onOpenTrader} />
    </TipHost>
  );
}

function stocksChip(board: CryptoBoard): string {
  const c = board.clock;
  const words = c.stock_session === 'closed' ? 'US stocks closed' : c.stock_session === 'regular' ? 'US stocks open' : c.stock_session === 'premarket' ? 'US premarket' : 'US after hours';
  if (!c.stock_next) return words;
  const next = c.stock_next.kind === 'premarket' ? 'premarket' : c.stock_next.kind === 'open' ? 'open' : c.stock_next.kind === 'close' ? 'close' : 'after hours ends';
  return `${words} · ${next} in ${countdown(c.stock_next.at - c.now)}`;
}

function Head({ board }: { board: CryptoBoard | null }) {
  const tip = useTip();
  return (
    <div className="cx-head">
      <h2 className="cx-head__title">{CRYPTOS_TITLE}</h2>
      <p className="cx-head__sub">{CRYPTOS_SUB}</p>
      {board ? (
        <>
          {board.replay_desk ? <span className="cx-status is-note">{CRYPTOS_REPLAY_NOTE}</span> : null}
          <span className="cx-status is-open" tabIndex={0} {...tip(() => tipCryptoOpen(board.clock))}>● Crypto open 24/7</span>
          <span className="cx-status" tabIndex={0} {...tip(() => tipStocksStatus(board.clock))}>{stocksChip(board)}</span>
        </>
      ) : null}
    </div>
  );
}

function CryptosBody({ onOpenTrader }: CryptosPageProps) {
  const { data: board, error, unavailable } = useCryptoBoard();
  const [symbol, setSymbol] = useState(CHART_DEFAULT);
  const [tf, setTf] = useState<CandleTf>('15m');

  if (unavailable || !board || !board.enabled) {
    const words = unavailable ? CRYPTOS_OLD_API : board && !board.enabled ? CRYPTOS_OFF : error ?? 'Reading the crypto market …';
    return (
      <div className="cx-page" data-testid="cryptos-page">
        <Head board={null} />
        <p className="cx-page__state" role="status">{words}</p>
      </div>
    );
  }

  return (
    <div className="cx-page" data-testid="cryptos-page">
      <Head board={board} />
      {error ? <p className="cx-page__stale" role="status">{error} -- showing the last good answer.</p> : null}
      <KpiStrip board={board} />
      <div className="cx-main">
        <CoinsCard board={board} selected={symbol} onSelect={setSymbol} onOpenTrader={onOpenTrader} />
        <div className="cx-side">
          <ChartCard board={board} symbol={symbol} tf={tf} onSymbol={setSymbol} onTf={setTf} />
          <ClockCard clock={board.clock} />
        </div>
      </div>
      <div className="cx-bottom">
        <BridgeCard board={board} onOpenTrader={onOpenTrader} />
        <LeverageCard board={board} />
        <FlowsCard board={board} />
        <NextNewsCard board={board} />
      </div>
    </div>
  );
}
