/**
 * Historical replay Time & Sales -- the live TimeSalesView fed from the Sim
 * snapshot (reached prints, newest first) instead of the tape WebSocket.
 */
import { useMemo } from 'react';
import { TimeSalesView, type TapePrint, type TapeState } from '../ibkr';
import { sourceLabel } from './historicalReplayFormat';
import { isMassive } from './historicalTypes';
import { playheadBeyondCoverage } from './simCoverage';
import {
  SIM_REPLAY_TAPE_EMPTY,
  SIM_REPLAY_TAPE_NO_TRADES,
  SIM_REPLAY_TAPE_SIDES_NBBO,
  SIM_REPLAY_TAPE_SIDES_NBBO_MISSING,
  SIM_REPLAY_TAPE_SIDES_NBBO_NONE,
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
  // The resource parses snapshots at the boundary; a hand-built one still never crashes the tape (C9).
  const rows = Array.isArray(snapshot.prints) ? snapshot.prints : [];
  const prints: TapePrint[] = rows.map(p => ({
    symbol: snapshot.symbol,
    replayId: p.ordinal == null ? undefined : `${snapshot.selection?.job_id ?? snapshot.symbol}:${p.ordinal}`,
    time: p.time,
    price: p.price,
    size: p.size,
    exchange: p.exchange ?? '',
    conditions: p.conditions ?? '',
    // A side exists only where a real quote decided it: the local L2 recording
    // (the quote held across the print's second) or a Massive window's NBBO (the
    // quote standing just before the print). Otherwise unknown -- never inferred.
    side: p.side ?? 'unknown',
    bid: p.bid ?? null,
    ask: p.ask ?? null,
    unreported: Boolean(p.unreported),
    // A Massive print that moves no price (odd lot, average price, busted) is dimmed like the live tape's (#543).
    setsPrice: p.sets_price !== false,
  }));
  return { prints, connected: true, error: prints.length ? null : snapshot.error ?? null };
}

/** Where the tape's colours come from, for its status title. */
export function tapeSidesTitle(snapshot: HistoricalSnapshot): string {
  if (isMassive(snapshot.selection)) {
    if (snapshot.quote_status === 'not_downloaded') return SIM_REPLAY_TAPE_SIDES_NBBO_MISSING;
    if (snapshot.quote_status === 'none') return SIM_REPLAY_TAPE_SIDES_NBBO_NONE;
    return SIM_REPLAY_TAPE_SIDES_NBBO;
  }
  return (snapshot.sides_recorded ?? 0) > 0 ? SIM_REPLAY_TAPE_SIDES_RECORDED : SIM_REPLAY_TAPE_SIDES_NONE;
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
    {snapshot.error && feed.prints.length > 0 && <p role="alert" className="sim-error">Replay update failed; showing last reached data. {snapshot.error}</p>}
    <TimeSalesView
      symbol={symbol}
      feed={feed}
      embedded
      uiActive={uiActive}
      connectedText={SIM_REPLAY_TAPE_STATUS}
      statusTitle={`${sourceLabel(snapshot)}. ${tapeSidesTitle(snapshot)}`}
      emptyLabel={emptyLabel}
    />
    </>
  );
}
