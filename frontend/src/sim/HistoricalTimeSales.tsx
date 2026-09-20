/**
 * Historical replay Time & Sales -- the live TimeSalesView fed from the Sim
 * snapshot (reached prints, newest first) instead of the tape WebSocket.
 */
import { useMemo } from 'react';
import { TimeSalesView, type TapePrint, type TapeState } from '../ibkr';
import { sourceLabel } from './historicalReplayFormat';
import {
  SIM_REPLAY_TAPE_EMPTY,
  SIM_REPLAY_TAPE_NO_TRADES,
  SIM_REPLAY_TAPE_STATUS,
} from './simConstants';
import type { HistoricalSnapshot } from './useHistoricalSnapshot';

interface Props {
  symbol: string;
  snapshot: HistoricalSnapshot;
  uiActive?: boolean;
}

export function historicalTapeFeed(snapshot: HistoricalSnapshot): TapeState {
  const prints: TapePrint[] = snapshot.prints.map(p => ({
    symbol: snapshot.symbol,
    replayId: p.ordinal == null ? undefined : `${snapshot.selection?.job_id ?? snapshot.symbol}:${p.ordinal}`,
    time: p.time,
    price: p.price,
    size: p.size,
    exchange: p.exchange ?? '',
    conditions: p.conditions ?? '',
    // No historical quotes are downloaded, so there is no bid/ask aggressor side.
    side: 'unknown',
    bid: null,
    ask: null,
    unreported: Boolean(p.unreported),
  }));
  return { prints, connected: true, error: prints.length ? null : snapshot.error ?? null };
}

export function HistoricalTimeSales({ symbol, snapshot, uiActive = true }: Props) {
  const feed = useMemo(() => historicalTapeFeed(snapshot), [snapshot]);
  const noTrades = snapshot.source === 'completed_bars';
  return (
    <>
    {snapshot.error && snapshot.prints.length > 0 && <p role="alert" className="sim-error">Replay update failed; showing last reached data. {snapshot.error}</p>}
    <TimeSalesView
      symbol={symbol}
      feed={feed}
      embedded
      uiActive={uiActive}
      connectedText={SIM_REPLAY_TAPE_STATUS}
      statusTitle={sourceLabel(snapshot)}
      emptyLabel={noTrades ? SIM_REPLAY_TAPE_NO_TRADES : SIM_REPLAY_TAPE_EMPTY}
    />
    </>
  );
}
