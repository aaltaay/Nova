/**
 * Compact Time & Sales tape — newest print on top.
 * Owns useIbkrTape (same pattern as DepthLadder → useIbkrDepth).
 * Row highlight = aggressor vs BBO at print time:
 *   ask (green) | bid (red) | between/unknown (black/neutral).
 */
import { useMemo } from 'react';
import {
  TAPE_COL_HEADERS,
  TAPE_SECTION_TITLE,
  TAPE_SIDE_LABELS,
} from '../constants';
import { useIbkrTape, type TapeSide } from './useIbkrTape';

interface Props {
  symbol: string | null;
  /** Parent rail: pane chrome + LIVE; no duplicate outer card title. */
  embedded?: boolean;
}

function fmtTime(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
  } catch {
    return iso.slice(11, 19) || iso;
  }
}

function fmtPrice(p: number): string {
  return p.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 4 });
}

function fmtSize(s: number): string {
  return s.toLocaleString('en-US');
}

function sideClass(side: TapeSide | undefined): string {
  switch (side) {
    case 'ask':
      return 'ts-row--ask';
    case 'bid':
      return 'ts-row--bid';
    case 'between':
      return 'ts-row--mid';
    default:
      return 'ts-row--unknown';
  }
}

function sideLabel(side: TapeSide | undefined): string {
  if (side === 'ask') return TAPE_SIDE_LABELS.ask;
  if (side === 'bid') return TAPE_SIDE_LABELS.bid;
  if (side === 'between') return TAPE_SIDE_LABELS.between;
  return TAPE_SIDE_LABELS.unknown;
}

export function TimeSalesPanel({ symbol, embedded = false }: Props) {
  const { prints, connected, error } = useIbkrTape(symbol);

  const statusLabel = useMemo(() => {
    if (error) return error;
    if (!connected) return 'Connecting…';
    if (prints.length === 0) return 'Waiting for prints…';
    return null;
  }, [error, connected, prints.length]);

  const statusClass = `ts-panel__status ${connected ? 'ts-panel__status--live' : 'ts-panel__status--off'}`;
  const statusText = connected ? 'LIVE' : (error ? 'ERROR' : '…');

  const cols = (
    <div className="ts-panel__cols" data-testid="ts-panel-cols">
      <span className="ts-col--time">{TAPE_COL_HEADERS.time}</span>
      <span className="ts-col--price">{TAPE_COL_HEADERS.price}</span>
      <span className="ts-col--size">{TAPE_COL_HEADERS.size}</span>
      <span className="ts-col--side">{TAPE_COL_HEADERS.side}</span>
      <span className="ts-col--exch">{TAPE_COL_HEADERS.exchange}</span>
    </div>
  );

  const rows = (
    <div className="ts-panel__rows">
      {statusLabel ? (
        <div className="ts-panel__empty">{statusLabel}</div>
      ) : (
        prints.map((p, i) => (
          <div key={`${p.time}-${i}`} className={`ts-row ${sideClass(p.side)}`}>
            <span className="ts-col--time">{fmtTime(p.time)}</span>
            <span className="ts-col--price">{fmtPrice(p.price)}</span>
            <span className="ts-col--size">{fmtSize(p.size)}</span>
            <span className="ts-col--side">{sideLabel(p.side)}</span>
            <span className="ts-col--exch">{p.exchange || '—'}</span>
          </div>
        ))
      )}
    </div>
  );

  if (embedded) {
    return (
      <div className="sv-md-pane ts-panel ts-panel--embedded">
        <div className="sv-md-pane__head">
          <h3 className="sv-md-pane__title">{TAPE_SECTION_TITLE}</h3>
          <span className={statusClass}>{statusText}</span>
        </div>
        <div className="sv-md-pane__body">
          {cols}
          {rows}
        </div>
      </div>
    );
  }

  return (
    <div className="ts-panel">
      <div className="ts-panel__header">
        <span className="ts-panel__title">{TAPE_SECTION_TITLE}</span>
        <span className={statusClass}>{statusText}</span>
      </div>
      {cols}
      {rows}
    </div>
  );
}
