/**
 * The Following page (operator ask 2026-10-13; redesign approved the same day, mockup "E2"): what each followed
 * trader holds now and closed that day, priced with Nova's IBKR data, the proof behind every trade, the stream they
 * trade on, and any past day the feed has. It fills the window with no page scrollbar: a head row, one block per
 * trader top to bottom, and the stream above the Activity on the right. Every state is said, never an empty list.
 * The rail shows it only when the backend has a feed configured (enabledStore). Schema:
 * architecture/schema/followed-traders.md. Nothing here places, stages or cancels an order.
 */
import { useEffect, useRef, useState } from 'react';
import { ActivityFeed } from './ActivityFeed';
import { offAirWhy, onAir } from './capture';
import { FT_ALL_CLOSED, FT_CLOSE_LIST, FT_LOADING, FT_NO_TRADES, FT_OFF, FT_READ_FAILED } from './constants';
import { fitPlan, maxFitLevel, useFitLevel } from './fit';
import { clearFollowedProofRequest, useFollowedProofRequest } from './followedStores';
import { PageHead } from './PageHead';
import { ProofView } from './ProofView';
import { roster } from './roster';
import { streamId, useStreamOpen } from './stream';
import { StreamOffAir, StreamPlayer } from './StreamPlayer';
import { ClosedTable } from './TradeTables';
import { TraderBlock } from './TraderBlock';
import type { FollowedDay, FollowedRecord, RecordRange } from './types';
import { useFollowedDay } from './useFollowedDay';
import { useFollowedRecord } from './useFollowedFetch';
import './followed.css';

interface Props {
  onOpenTrader?: (symbol: string) => void;
}

export function FollowedTradersPage(_props: Props) {
  // null: the feed's own today. Each day mounts its own reader, so two days' answers never mix.
  const [date, setDate] = useState<string | null>(null);
  const [proofId, setProofId] = useState<string | null>(null);
  const [range, setRange] = useState<RecordRange>('day');
  const request = useFollowedProofRequest();

  useEffect(() => {
    if (!request) return;
    setDate(request.date);
    setProofId(request.tradeId);
    clearFollowedProofRequest();
  }, [request]);

  const pick = (next: string | null) => {
    setProofId(null);
    setDate(next);
  };
  return (
    <div className="ft-page" data-testid="followed-traders-page">
      <DayView key={date ?? 'today'} date={date} proofId={proofId} range={range} onRange={setRange}
        onPickDate={pick} onProof={setProofId} />
    </div>
  );
}

interface DayViewProps {
  date: string | null;
  proofId: string | null;
  range: RecordRange;
  onRange: (r: RecordRange) => void;
  onPickDate: (date: string | null) => void;
  onProof: (id: string | null) => void;
}

function DayView(props: DayViewProps) {
  const { data, error, off } = useFollowedDay(props.date);
  if (off) return <p className="ft-state" data-testid="ft-state">{FT_OFF}</p>;
  if (!data) return <p className="ft-state" data-testid="ft-state">{error ? `${FT_READ_FAILED} ${error}` : FT_LOADING}</p>;
  return <DayBody day={data} error={error} {...props} />;
}

function DayBody({ day, error, proofId, range, onRange, onPickDate, onProof }: DayViewProps & { day: FollowedDay; error: string | null }) {
  const ok = day.feed.state === 'ok';
  const isToday = day.date !== null && day.date === day.today;
  const records = useFollowedRecord(range, day.date);
  const streamOpen = useStreamOpen();
  const c = day.capture;
  // The stream is the feed's now, whatever day is shown: watching it never depends on the day picked. It plays only
  // while the feed reads it live; off air its place says so, never replaying the ended broadcast.
  const videoId = streamId(c?.video_id);
  const streamLive = onAir(c);
  const hasOpen = day.traders.some((t) => t.open.length > 0);
  const pricesWhy = isToday && hasOpen && day.prices && day.prices.state !== 'live' ? day.prices.why : null;
  const recordFor = (name: string, own: FollowedRecord): FollowedRecord | null =>
    range === 'day' ? own : records.data?.traders.find((t) => t.name === name)?.record ?? null;
  const proofOwner = proofId ? day.traders.find((t) => [...t.open, ...t.closed].some((x) => x.id === proofId)) : null;
  const proofTrade = proofOwner ? [...proofOwner.open, ...proofOwner.closed].find((x) => x.id === proofId) ?? null : null;
  return (
    <>
      <PageHead day={day} onPickDate={onPickDate} pricesWhy={pricesWhy} stream={{ id: videoId, open: streamOpen, live: streamLive,
        offAirWhy: c && !streamLive ? offAirWhy(c) : null }}
        records={ok ? { range, onRange, overall: range === 'day' ? day.overall : records.data?.overall ?? null,
          error: records.error, pending: records.data?.pending ?? 0 } : null} />
      {error && <p className="ft-state ft-state--warn">{FT_READ_FAILED} {error} · showing the last answer</p>}
      {ok && proofTrade && proofOwner && day.date ? (
        <div className="ft-main ft-main--proof">
          <ProofView trade={proofTrade} face={proofOwner.face} date={day.date} generatedAt={day.generated_at}
            onBack={() => onProof(null)} />
        </div>
      ) : ok && (
        <div className="ft-main">
          <Board day={day} isToday={isToday} recordFor={recordFor} onProof={onProof} />
          <aside className="ft-rail">
            {videoId && streamOpen && c && (streamLive
              ? <StreamPlayer videoId={videoId} title={c.title} />
              : <StreamOffAir capture={c} />)}
            <ActivityFeed traders={day.traders} onProof={onProof} />
          </aside>
        </div>
      )}
    </>
  );
}

interface BoardProps {
  day: FollowedDay;
  isToday: boolean;
  recordFor: (name: string, own: FollowedRecord) => FollowedRecord | null;
  onProof: (id: string) => void;
}

/** Every trader's block, top to bottom, shrunk and folded until it fits (fit.ts); a list over it shows one's all. */
function Board({ day, isToday, recordFor, onProof }: BoardProps) {
  const stack = useRef<HTMLDivElement>(null);
  const [showAll, setShowAll] = useState<string | null>(null);
  const people = roster(day, isToday);
  const closed: [string, number][] = people.map((e) => [e.name, e.trader?.closed.length ?? 0]);
  const shape = people.map((e) => `${e.name}:${e.trader?.open.map((t) => t.id).join('+')}/${e.trader?.closed.map((t) => t.id).join('+')}`).join('|');
  const { level, overflowing } = useFitLevel(stack, shape, maxFitLevel(closed));
  const plan = fitPlan(level, closed);
  const c = day.capture;
  const live = onAir(c);
  const lastRead = c && !live && c.clock ? c.clock : null;
  const listed = showAll ? people.find((e) => e.name === showAll)?.trader ?? null : null;
  return (
    <div className="ft-board">
      <div className={`ft-stack${overflowing ? ' is-overflowing' : ''}`} ref={stack} data-testid="ft-stack" data-fit-level={level}>
        {people.length === 0 && <div className="ft-empty">{FT_NO_TRADES}</div>}
        {people.map((e) => (
          <TraderBlock key={e.name} entry={e} isToday={isToday}
            record={e.trader ? recordFor(e.name, e.trader.record) : null}
            onAir={isToday && live && (c?.traders.includes(e.name) ?? false)} captureVersion={c?.updated_at ?? null}
            lastRead={lastRead} compact={plan.compact} folded={plan.folded[e.name] ?? 0} onShowAll={setShowAll}
            onProof={onProof} />
        ))}
      </div>
      {listed && (
        <div className="ft-overlay" role="dialog" aria-label={`${listed.name}: ${FT_ALL_CLOSED}`} data-testid="ft-closed-all">
          <div className="ft-overlay__head">
            <h2 className="ft-eyebrow">{listed.name} · {FT_ALL_CLOSED} ({listed.closed.length})</h2>
            <button type="button" className="ft-btn" onClick={() => setShowAll(null)}>{FT_CLOSE_LIST}</button>
          </div>
          <div className="ft-overlay__body">
            <ClosedTable trades={listed.closed} onProof={(id) => { setShowAll(null); onProof(id); }} />
          </div>
        </div>
      )}
    </div>
  );
}
