/**
 * Scan's HOD Momo and Running Up lists (mockup v1, 2026-11-18): the desk's alert feed, one row per stock,
 * the newest first catch on top. Under the chip: what fired last, when the stock first alerted today, and
 * how many alerts it has raised. A list longer than the screen pages; nothing scrolls. Tap a row for the
 * stock page, the blue chip for the Trader.
 */
import { useLayoutEffect, useRef, useState } from 'react';
import { Star } from 'lucide-react';
import { howListed, useHotList } from '../../hot_list';
import { RowLink, TickerChip } from '../PhoneChrome';
import { compact, pct1, px, rvolShort, toneOf } from '../phoneFormat';
import { hodRowIsNew, type PhoneHodList, type PhoneHodRow } from '../phoneHod';
import { go } from '../phoneRoute';
import { notifySummary } from '../notify/phoneNotify';
import { usePhoneNotify } from '../notify/usePhoneNotify';
import { usePhoneHodMomo } from '../usePhoneHodMomo';
import { useRowsThatFit } from '../useRowsThatFit';

const ROW_PX = 42;
const LIST_NAME: Record<PhoneHodList, string> = { hod_momo: 'HOD Momo', running_up: 'Running Up' };

function HodRow({ row, starred, isNew }: { row: PhoneHodRow; starred: boolean; isNew: boolean }) {
  const tone = toneOf(row.change == null ? null : row.change * 100, 1);
  return (
    <div className={`ph-scan__row${isNew ? ' ph-hod__new' : ''}`} data-testid={`phone-hod-row-${row.symbol}`}>
      <div className="ph-scan__sym">
        <TickerChip symbol={row.symbol} />
        <div className="ph-scan__cat ph-hod__cat">
          <b>{row.strategy}</b>
          <span>
            <em>{row.at} · ×{row.count.toLocaleString('en-US')}</em>
            {starred ? <Star className="ph-scan__star" size={9} fill="currentColor" aria-label="On your hot list" /> : null}
          </span>
        </div>
      </div>
      <div className="ph-scan__px">{px(row.price)}</div>
      <div className="ph-scan__chg"><span data-tone={tone || 'flat'}>{pct1(row.change)}</span></div>
      <div className="ph-scan__vol">
        <span>{compact(row.volume)}</span>
        <i>{rvolShort(row.rvol)}</i>
      </div>
      <div className="ph-scan__flt">{compact(row.float)}</div>
      <RowLink symbol={row.symbol} />
    </div>
  );
}

export function ScanHod({ list, nowMs }: { list: PhoneHodList; nowMs: number }) {
  const feed = usePhoneHodMomo();
  const hot = useHotList();
  const notify = usePhoneNotify();
  const [page, setPage] = useState(0);
  const bodyRef = useRef<HTMLDivElement>(null);
  const perPage = useRowsThatFit(bodyRef, ROW_PX);
  const rows = list === 'running_up' ? feed.runningUp : feed.hodMomo;

  const pages = Math.max(1, Math.ceil(rows.length / perPage));
  const at = Math.min(page, pages - 1);
  useLayoutEffect(() => {
    if (at !== page) setPage(at);
  }, [at, page]);
  // A new list starts on its first page.
  useLayoutEffect(() => {
    setPage(0);
  }, [list]);
  const shown = rows.slice(at * perPage, at * perPage + perPage);
  const empty = rows.length ? null : feed.absence ?? `${LIST_NAME[list]}: no alerts yet today.`;

  return (
    <div className="ph-hod" data-testid={`phone-hod-${list}`}>
      <div className="ph-hod__info">
        <span>{rows.length === 1 ? '1 stock today' : `${rows.length} stocks today`} · newest first</span>
        <button type="button" className="ph-hod__notify" data-testid="phone-hod-notify" onClick={() => go({ screen: 'notify' })}>
          Notifications <b data-on={notify.thisPhone === 'on'}>{notifySummary(notify.view, notify.thisPhone, 'short')}</b> ›
        </button>
      </div>
      <div className="ph-scan__head">
        <div>Symbol · alert · time</div>
        <div>Price</div>
        <div>Change</div>
        <div>Volume</div>
        <div>Float</div>
      </div>
      <div className="ph-scan__rows" ref={bodyRef} data-testid="phone-hod-rows">
        {empty ? <div className="ph-empty" role="status">{empty}</div> : shown.map((row) => (
          <HodRow key={row.symbol} row={row} starred={howListed(hot.view, row.symbol) === 'star'} isNew={hodRowIsNew(row, nowMs)} />
        ))}
      </div>
      <div className="ph-scan__foot">
        <div data-testid="phone-hod-count">
          {rows.length ? `${at * perPage + 1} to ${Math.min(rows.length, (at + 1) * perPage)} of ${rows.length}` : '0 stocks'}
        </div>
        <div className="ph-scan__pager">
          <button type="button" className="ph-pill-btn" disabled={at === 0} data-why="This is the first page." onClick={() => setPage(at - 1)}>‹ Prev</button>
          <button type="button" className="ph-pill-btn" disabled={at >= pages - 1} data-why="This is the last page." onClick={() => setPage(at + 1)}>Next ›</button>
        </div>
      </div>
    </div>
  );
}
