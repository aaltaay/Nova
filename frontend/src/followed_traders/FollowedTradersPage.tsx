/**
 * The Following page (operator ask 2026-10-13; the design canvas "Followed Traders UX", four boards): what each
 * followed trader holds now, their entries and exits, priced with Nova's IBKR data, the proof behind every trade,
 * and any past day the feed has. Every state is said, never an empty list. The rail shows it only when the backend
 * has a feed configured (enabledStore). Schema: architecture/schema/followed-traders.md. Nothing here places,
 * stages or cancels an order.
 */
import { useEffect, useState } from 'react';
import { ActivityFeed } from './ActivityFeed';
import { BarNow } from './BarNow';
import { captureStopped } from './capture';
import {
  FT_EVERYONE,
  FT_LOADING,
  FT_NO_TRADES,
  FT_OFF,
  FT_READ_FAILED,
  FT_RECORD_PENDING,
  FT_RECORD_RANGES,
  FT_RECORDS,
} from './constants';
import { clearFollowedProofRequest, useFollowedProofRequest } from './followedStores';
import { PageHead } from './PageHead';
import { RecordChips } from './parts';
import { ProofView } from './ProofView';
import { TraderSection } from './TraderSection';
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

function DayView({ date, proofId, range, onRange, onPickDate, onProof }: DayViewProps) {
  const { data, error, off } = useFollowedDay(date);
  if (off) return <p className="ft-state" data-testid="ft-state">{FT_OFF}</p>;
  if (!data) return <p className="ft-state" data-testid="ft-state">{error ? `${FT_READ_FAILED} ${error}` : FT_LOADING}</p>;
  return (
    <>
      <PageHead day={data} onPickDate={onPickDate} />
      {error && <p className="ft-state ft-state--warn">{FT_READ_FAILED} {error} · showing the last answer</p>}
      {data.feed.state === 'ok' && <DayBody day={data} proofId={proofId} range={range} onRange={onRange} onProof={onProof} />}
    </>
  );
}

function DayBody({ day, proofId, range, onRange, onProof }: { day: FollowedDay; proofId: string | null;
  range: RecordRange; onRange: (r: RecordRange) => void; onProof: (id: string | null) => void }) {
  const isToday = day.date !== null && day.date === day.today;
  const records = useFollowedRecord(range, day.date);
  const proofOwner = proofId ? day.traders.find((t) => [...t.open, ...t.closed].some((x) => x.id === proofId)) : null;
  const proofTrade = proofOwner ? [...proofOwner.open, ...proofOwner.closed].find((x) => x.id === proofId) ?? null : null;
  if (proofTrade && proofOwner && day.date) {
    return <ProofView trade={proofTrade} face={proofOwner.face} date={day.date} generatedAt={day.generated_at}
      onBack={() => onProof(null)} />;
  }
  const c = day.capture;
  const live = c !== null && c.live && !captureStopped(c);
  const hasOpen = day.traders.some((t) => t.open.length > 0);
  const recordFor = (name: string, own: FollowedRecord): FollowedRecord | null =>
    range === 'day' ? own : records.data?.traders.find((t) => t.name === name)?.record ?? null;
  const overall = range === 'day' ? day.overall : records.data?.overall ?? null;
  return (
    <>
      {isToday && c && <BarNow capture={c} traders={day.traders} />}
      {isToday && hasOpen && day.prices && day.prices.state !== 'live' && (
        <p className="ft-state ft-state--warn" data-testid="ft-prices">Prices now: {day.prices.why}</p>
      )}
      <div className="ft-records" data-testid="ft-records">
        <span className="ft-eyebrow">{FT_RECORDS}</span>
        <div className="ft-segmented" role="group" aria-label={FT_RECORDS}>
          {(Object.keys(FT_RECORD_RANGES) as RecordRange[]).map((r) => (
            <button key={r} type="button" aria-pressed={range === r} className={range === r ? 'is-on' : undefined}
              onClick={() => onRange(r)} data-testid={`ft-range-${r}`}>{FT_RECORD_RANGES[r]}</button>
          ))}
        </div>
        <span className="ft-muted ft-small">{FT_EVERYONE}</span>
        <RecordChips record={overall} testId="ft-record-everyone" />
        {range !== 'day' && records.error && <span className="ft-small ft-warn-text">{records.error}</span>}
        {range !== 'day' && (records.data?.pending ?? 0) > 0 && (
          <span className="ft-small ft-muted">{records.data?.pending} {FT_RECORD_PENDING}</span>
        )}
      </div>
      <div className="ft-columns">
        <div className="ft-traders">
          {day.traders.length === 0 && <div className="ft-empty">{FT_NO_TRADES}</div>}
          {day.traders.map((t) => (
            <TraderSection key={t.name} trader={t} record={recordFor(t.name, t.record)} isToday={isToday}
              onAir={isToday && live && (c?.traders.includes(t.name) ?? false)} onProof={onProof} />
          ))}
        </div>
        <ActivityFeed traders={day.traders} onProof={onProof} />
      </div>
    </>
  );
}
