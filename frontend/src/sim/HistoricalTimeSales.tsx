/**
 * Historical replay Time & Sales -- the live TimeSalesView fed from the Sim
 * snapshot (reached prints, newest first) instead of the tape WebSocket.
 */
import { useMemo } from 'react';
import { TimeSalesView, type TapePrint, type TapeState } from '../ibkr';
import { sourceLabel } from './historicalReplayFormat';
import { playheadBeyondCoverage } from './simCoverage';
import {
  SIM_REPLAY_TAPE_EMPTY,
  SIM_REPLAY_TAPE_NO_TRADES,
  SIM_REPLAY_TAPE_SIDES_NONE,
  SIM_REPLAY_TAPE_SIDES_RECORDED,
  SIM_REPLAY_TAPE_STATUS,
  simReplayTapeNotDownloaded,
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
    // A side exists only where the local L2 recording decided it (the quote held
    // across the print's second). Otherwise unknown -- never inferred.
    side: p.side ?? 'unknown',
    bid: p.bid ?? null,
    ask: p.ask ?? null,
    unreported: Boolean(p.unreported),
  }));
  return { prints, connected: true, error: prints.length ? null : snapshot.error ?? null };
}

export function HistoricalTimeSales({ symbol, snapshot, uiActive = true }: Props) {
  // Past the download edge the reached prints are the edge's, not this moment's.
  const beyond = playheadBeyondCoverage(snapshot);
  const feed = useMemo(
    () => (beyond ? { prints: [], connected: true, error: null } : historicalTapeFeed(snapshot)),
    [snapshot, beyond],
  );
  const noTrades = snapshot.source === 'completed_bars';
  // A running download was pointed here by the scrub (history_download.follow_playhead).
  const fetching = snapshot.selection?.download_status === 'running';
  const emptyLabel = beyond
    ? simReplayTapeNotDownloaded(fetching)
    : noTrades ? SIM_REPLAY_TAPE_NO_TRADES : SIM_REPLAY_TAPE_EMPTY;
  return (
    <>
    {snapshot.error && snapshot.prints.length > 0 && <p role="alert" className="sim-error">Replay update failed; showing last reached data. {snapshot.error}</p>}
    <TimeSalesView
      symbol={symbol}
      feed={feed}
      embedded
      uiActive={uiActive}
      connectedText={SIM_REPLAY_TAPE_STATUS}
      statusTitle={`${sourceLabel(snapshot)} ${(snapshot.sides_recorded ?? 0) > 0
        ? SIM_REPLAY_TAPE_SIDES_RECORDED : SIM_REPLAY_TAPE_SIDES_NONE}`}
      emptyLabel={emptyLabel}
    />
    </>
  );
}
