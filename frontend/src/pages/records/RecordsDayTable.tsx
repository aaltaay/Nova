/**
 * Records › Market data's table (operator ask 2026-10-14): the newest day open,
 * one row per symbol with a coverage bar on a clock every day shares, time
 * recorded, prints, book updates, gaps, who ended it and its size; filter chips
 * and a symbol search; earlier days folded to one line each that opens on a
 * click. Recording rows stay on top and carry a held Stop.
 */
import { useMemo, useState } from 'react';
import { captureStopHoldLabel, HoldToStopButton, stopTabRecord } from '../../capture';
import { recordingUsable, recordPrintsCell } from '../../sim/captureRowFormat';
import { CAPTURE_PRINTS_RECORDING } from '../../sim/simConstants';
import type { CaptureSessionRow } from '../../sim/useSimSessionController';
import { SortTh, useTableSort, type SortColumns } from '../../table_sort';
import { whyProps } from '../../ux/whyTip';
import { CoverageBar } from './CoverageBar';
import {
  RECORDS_COL_BOOK,
  RECORDS_COL_ENDED,
  RECORDS_COL_GAPS,
  RECORDS_COL_PRINTS,
  RECORDS_COL_RECORDED,
  RECORDS_COL_SIZE,
  RECORDS_COL_SYMBOL,
  RECORDS_COVERAGE_LABEL,
  RECORDS_DAYS_PAGE,
  RECORDS_EARLIER_DAYS,
  RECORDS_ENDED_DEFAULT_SORT,
  RECORDS_FILTER_PLACEHOLDER,
  RECORDS_FILTERS,
  RECORDS_GAP_WHY,
  RECORDS_GAP_WHY_UNKNOWN,
  RECORDS_GAPS_NONE,
  RECORDS_HIDE_DAY,
  RECORDS_LEGEND_LIVE,
  RECORDS_LEGEND_MARKET,
  RECORDS_LEGEND_MISSING,
  RECORDS_LEGEND_PLANNED,
  RECORDS_LEGEND_RECORDED,
  RECORDS_NO_MATCH,
  RECORDS_OPEN_TRADER,
  RECORDS_REPLAY,
  RECORDS_REPLAY_BUSY,
  RECORDS_REPLAY_TITLE,
  RECORDS_STOP_FAILED,
  RECORDS_STOP_SHORT,
  RECORDS_TODAY,
  recordsDayCut,
  recordsDayGaps,
  recordsDaySymbols,
  recordsEndedAt,
  recordsGapTitle,
  recordsShowDay,
  recordsShowMoreDays,
} from './recordsConstants';
import {
  axisFor,
  bytesLabel,
  counted,
  dayLabel,
  daySummary,
  durationLabel,
  endedOf,
  etClock,
  etMinute,
  formatMissingSeconds,
  gapKinds,
  hm,
  hourTicks,
  lastStop,
  matchesFilter,
  newestFirst,
  pct,
  recordedSec,
  rowBytes,
  type Axis,
  type DayRecord,
  type RecordsFilter,
} from './recordsModel';
import { TickerLink } from '../../components/TickerLink';

interface Props {
  byDay: Record<string, CaptureSessionRow[]>;
  /** Fresh recording symbols: only today's row can be one. */
  recording: ReadonlySet<string>;
  today: string;
  nowSec: number;
  sim: boolean;
  replayBusy: boolean;
  onReplay: (date: string, symbol: string) => void;
  onOpenTrader: (symbol: string) => void;
}

const COLUMNS: SortColumns<DayRecord> = {
  symbol: r => r.row.symbol,
  recorded: r => recordedSec(r.row),
  prints: r => counted(r.row.prints),
  l2: r => counted(r.row.l2),
  gaps: r => counted(r.row.missing_sec),
  ended: r => lastStop(r.row),
  size: r => rowBytes(r.row),
};

function gapTitle(row: CaptureSessionRow): string | undefined {
  const lines = (row.gaps ?? []).map(([a, b, reason]) =>
    recordsGapTitle(etClock(a), etClock(b), (reason && RECORDS_GAP_WHY[reason]) || RECORDS_GAP_WHY_UNKNOWN));
  return lines.length ? lines.join('\n') : undefined;
}

function RecordRow({ rec, axis, nowSec, sim, replayBusy, onReplay, onOpenTrader }: {
  rec: DayRecord; axis: Axis; nowSec: number; sim: boolean; replayBusy: boolean;
  onReplay: (date: string, symbol: string) => void; onOpenTrader: (symbol: string) => void;
}) {
  const [stopError, setStopError] = useState<string | null>(null);
  const { row, live, ended, date } = rec;
  const { missing, planned } = gapKinds(row);
  const missingSec = row.missing_sec ?? 0;
  const bytes = rowBytes(row);
  const end = lastStop(row);
  const l2 = counted(row.l2);
  return (
    <tr className={live ? 'is-live' : undefined} data-testid={`records-row-${date}-${row.symbol}`}>
      <td className="records-table__sym">{live && <span className="records-pulse" aria-hidden="true" />}<TickerLink symbol={row.symbol} look="own" /></td>
      <td className="records-table__cov">
        <CoverageBar spans={row.spans ?? []} missing={missing} planned={planned} axis={axis} live={live} nowSec={nowSec} />
      </td>
      <td className="is-num">{durationLabel(recordedSec(row))}</td>
      <td className="is-num">{recordPrintsCell(row.prints, live)}</td>
      <td className="is-num">{l2 != null ? l2.toLocaleString() : live ? CAPTURE_PRINTS_RECORDING : '--'}</td>
      <td className={`is-num records-gaps${missingSec > 0 ? ' has' : ''}`} title={gapTitle(row)}>
        {missingSec > 0 ? formatMissingSeconds(missingSec) : <span className="records-dim">{RECORDS_GAPS_NONE}</span>}
      </td>
      <td>
        <span className={`records-ended is-${ended.tone}`} title={!live && end != null ? recordsEndedAt(etClock(end)) : undefined}>
          {(ended.tone === 'live' || ended.tone === 'warn') && <span className="records-ended__dot" aria-hidden="true" />}
          {ended.words}
        </span>
        {stopError && <div className="records-bad" role="alert">{RECORDS_STOP_FAILED} {stopError}</div>}
      </td>
      <td className="is-num records-dim">{bytes != null ? bytesLabel(bytes) : '--'}</td>
      <td className="records-table__act">
        {live && (
          <HoldToStopButton role="button" label={captureStopHoldLabel(row.symbol)}
            onConfirm={() => void stopTabRecord(row.symbol).then(setStopError)}
            className="records-rowbtn records-rowbtn--stop" testId={`records-stop-${row.symbol}`}>
            <span className="records-btn__sq" aria-hidden="true" />{RECORDS_STOP_SHORT}
          </HoldToStopButton>
        )}
        {sim && recordingUsable(row) && (
          <button type="button" className="records-rowbtn" data-testid={`records-replay-${date}-${row.symbol}`}
            title={replayBusy ? undefined : RECORDS_REPLAY_TITLE} disabled={replayBusy}
            {...whyProps(replayBusy, RECORDS_REPLAY_BUSY)} onClick={() => onReplay(date, row.symbol)}>
            {RECORDS_REPLAY}
          </button>
        )}
        <button type="button" className="records-rowbtn" data-testid={`records-open-${date}-${row.symbol}`}
          onClick={() => onOpenTrader(row.symbol)}>
          {RECORDS_OPEN_TRADER}
        </button>
      </td>
    </tr>
  );
}

export function RecordsDayTable({ byDay, recording, today, nowSec, sim, replayBusy, onReplay, onOpenTrader }: Props) {
  const [filter, setFilter] = useState<RecordsFilter>('all');
  const [query, setQuery] = useState('');
  const [opened, setOpened] = useState<ReadonlySet<string>>(() => new Set());
  const [shownDays, setShownDays] = useState(RECORDS_DAYS_PAGE);
  const days = useMemo(() => Object.keys(byDay).filter(d => (byDay[d] ?? []).length > 0).sort().reverse(), [byDay]);
  const openDay = days.includes(today) ? today : days[0];
  const records = useMemo(() => {
    const out: DayRecord[] = [];
    for (const date of days) {
      for (const row of byDay[date] ?? []) {
        const live = date === today && recording.has(row.symbol);
        out.push({ date, row, live, ended: endedOf(row, live) });
      }
    }
    return out;
  }, [byDay, days, today, recording]);
  const { rows: sorted, sort, onSort } = useTableSort('records.sessions', records, COLUMNS);
  // Before any header is clicked: newest stop first. Either way the recording rows stay on top.
  const ordered = useMemo(() => {
    const base = sort ? sorted : [...records].sort(newestFirst);
    return [...base.filter(r => r.live), ...base.filter(r => !r.live)];
  }, [sort, sorted, records]);
  const earlier = days.filter(d => d !== openDay);
  const shown = earlier.slice(0, shownDays);
  const byDate = useMemo(() => {
    const map = new Map<string, DayRecord[]>();
    for (const r of records) map.set(r.date, [...(map.get(r.date) ?? []), r]);
    return map;
  }, [records]);
  // One clock for the open day and every earlier day shown, so their bars line up.
  const axis = useMemo(() => {
    const dates = [openDay, ...days.filter(d => d !== openDay).slice(0, shownDays)];
    return axisFor(dates.flatMap(d => (byDay[d ?? ''] ?? []).map(r => r.spans)));
  }, [byDay, days, openDay, shownDays]);
  if (!openDay) return null;
  const openRecords = byDate.get(openDay) ?? [];
  const summary = daySummary(openRecords);
  const counts: Record<RecordsFilter, number> = {
    all: summary.count, recording: summary.recording, gaps: summary.withGaps, cut: summary.cut, you: summary.byYou,
  };
  const visible = (date: string) => ordered.filter(r => r.date === date && matchesFilter(r, filter, query));
  const openRows = visible(openDay);
  const toggle = (date: string) => setOpened(prev => {
    const next = new Set(prev);
    if (next.has(date)) next.delete(date); else next.add(date);
    return next;
  });
  const rowProps = { axis, nowSec, sim, replayBusy, onReplay, onOpenTrader };
  const nowMin = etMinute(nowSec);

  return (
    <div className="records-day">
      <div className="records-dayhead">
        <h3>{dayLabel(openDay)}{openDay === today ? ` · ${RECORDS_TODAY}` : ''}</h3>
        <span className="records-dayhead__stats" data-testid="records-day-stats">
          <b>{summary.count}</b> recorded · <b>{summary.prints.toLocaleString()}</b> prints ·{' '}
          <span className={summary.withGaps ? 'records-warn' : undefined}><b>{summary.withGaps}</b> with gaps</span> ·{' '}
          <b>{summary.cut}</b> cut by a Nova restart · <b>{bytesLabel(summary.bytes)}</b> on disk
        </span>
      </div>
      <div className="records-toolbar">
        <input className="records-input records-filter" type="search" value={query} placeholder={`⌕ ${RECORDS_FILTER_PLACEHOLDER}`}
          aria-label={RECORDS_FILTER_PLACEHOLDER} data-testid="records-filter" onChange={e => setQuery(e.target.value)} />
        {RECORDS_FILTERS.filter(f => f.id === 'all' || f.id !== 'recording' || counts.recording > 0).map(f => (
          <button key={f.id} type="button" className={`records-chip${filter === f.id ? ' is-on' : ''}`} aria-pressed={filter === f.id}
            data-testid={`records-chip-${f.id}`} onClick={() => setFilter(f.id)}>
            {f.id === 'recording' && <i className="records-chip__dot is-live" aria-hidden="true" />}
            {f.id === 'gaps' && <i className="records-chip__dot is-warn" aria-hidden="true" />}
            {f.label} <b>{counts[f.id]}</b>
          </button>
        ))}
        <span className="records-legend" aria-hidden="true">
          <span><i className="records-legend__sw is-span" />{RECORDS_LEGEND_RECORDED}</span>
          <span><i className="records-legend__sw is-live" />{RECORDS_LEGEND_LIVE}</span>
          <span><i className="records-legend__sw is-missing" />{RECORDS_LEGEND_MISSING}</span>
          <span><i className="records-legend__sw is-planned" />{RECORDS_LEGEND_PLANNED}</span>
          <span><i className="records-legend__sw is-market" />{RECORDS_LEGEND_MARKET}</span>
        </span>
      </div>
      <table className="records-table" data-testid="records-page-table">
        <thead>
          <tr>
            <SortTh col="symbol" sort={sort} onSort={onSort}>{RECORDS_COL_SYMBOL}</SortTh>
            <th className="records-table__cov" aria-label={RECORDS_COVERAGE_LABEL}>
              <div className="records-covhead">
                {hourTicks(axis).map(m => <span key={m} style={{ left: `${pct(m, axis)}%` }}>{hm(m)}</span>)}
                {openDay === today && nowMin > axis.t0 && nowMin < axis.t1 && (
                  <span className="records-covhead__now" style={{ left: `${pct(nowMin, axis)}%` }} aria-hidden="true" />
                )}
              </div>
            </th>
            <SortTh col="recorded" sort={sort} onSort={onSort} className="is-num">{RECORDS_COL_RECORDED}</SortTh>
            <SortTh col="prints" sort={sort} onSort={onSort} className="is-num">{RECORDS_COL_PRINTS}</SortTh>
            <SortTh col="l2" sort={sort} onSort={onSort} className="is-num">{RECORDS_COL_BOOK}</SortTh>
            <SortTh col="gaps" sort={sort} onSort={onSort} className="is-num">{RECORDS_COL_GAPS}</SortTh>
            <SortTh col="ended" sort={sort} onSort={onSort}>
              {RECORDS_COL_ENDED}{!sort && <span className="records-table__default"> {RECORDS_ENDED_DEFAULT_SORT}</span>}
            </SortTh>
            <SortTh col="size" sort={sort} onSort={onSort} className="is-num">{RECORDS_COL_SIZE}</SortTh>
            <th />
          </tr>
        </thead>
        <tbody data-testid={`records-day-${openDay}`}>
          {openRows.map(rec => <RecordRow key={rec.row.symbol} rec={rec} {...rowProps} />)}
          {!openRows.length && (
            <tr><td colSpan={9} className="records-dim records-table__empty">{RECORDS_NO_MATCH}</td></tr>
          )}
        </tbody>
        {shown.length > 0 && (
          <tbody>
            <tr className="records-table__sep"><td colSpan={9}>{RECORDS_EARLIER_DAYS}</td></tr>
          </tbody>
        )}
        {shown.map(date => {
          const dayRecords = byDate.get(date) ?? [];
          const s = daySummary(dayRecords);
          const isOpen = opened.has(date);
          return (
            <tbody key={date} data-testid={`records-day-${date}`}>
              <tr className={`records-table__day${isOpen ? ' is-open' : ''}`} onClick={() => toggle(date)}>
                <td className="records-table__sym"><span className="records-chev" aria-hidden="true">{isOpen ? '⌄' : '›'}</span>{dayLabel(date)}</td>
                <td className="records-table__cov"><CoverageBar spans={s.union} axis={axis} /></td>
                <td className="is-num">{durationLabel(s.recordedSec)}</td>
                <td className="is-num">{s.prints.toLocaleString()}</td>
                <td className="is-num">{s.l2.toLocaleString()}</td>
                <td className={`is-num records-gaps${s.withGaps ? ' has' : ''}`}>
                  {s.withGaps ? recordsDayGaps(s.withGaps) : <span className="records-dim">{RECORDS_GAPS_NONE}</span>}
                </td>
                <td className="records-muted">
                  {recordsDaySymbols(s.count)}{s.cut > 0 && <> · <span className="records-warn">{recordsDayCut(s.cut)}</span></>}
                </td>
                <td className="is-num records-dim">{bytesLabel(s.bytes)}</td>
                <td className="records-table__act">
                  <button type="button" className="records-rowbtn" aria-expanded={isOpen} data-testid={`records-day-toggle-${date}`}
                    onClick={e => { e.stopPropagation(); toggle(date); }}>
                    {isOpen ? RECORDS_HIDE_DAY : recordsShowDay(s.count)}
                  </button>
                </td>
              </tr>
              {isOpen && visible(date).map(rec => <RecordRow key={rec.row.symbol} rec={rec} {...rowProps} />)}
            </tbody>
          );
        })}
      </table>
      {earlier.length > shown.length && (
        <button type="button" className="records-more" data-testid="records-more-days"
          onClick={() => setShownDays(n => n + RECORDS_DAYS_PAGE * 2)}>
          {recordsShowMoreDays(earlier.length - shown.length)}
        </button>
      )}
    </div>
  );
}
