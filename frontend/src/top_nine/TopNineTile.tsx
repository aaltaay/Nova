/**
 * One of the nine tiles: rank box, ticker, the switch pill while it is marked, the Change %, volume
 * and float, and the 1-minute chart. A switch lights the tile green (up), red (down) or blue (new to
 * the top nine) for TOP_NINE_MARK_FULL_MS, with a bar along the top edge running out; then a soft
 * tint stays on the rank box until TOP_NINE_MARK_SOFT_MS. A double-click anywhere on the tile, or a
 * click on the ticker (TickerLink, like every ticker on the desk), opens it in the desk's Trader. A
 * right-click opens the mute menu (TopNineTileMenu); a muted stock shows a crossed bell by its ticker.
 */
import { forwardRef } from 'react';
import { BellOff } from 'lucide-react';
import { TickerLink } from '../components/TickerLink';
import { fmtPct, fmtVolume } from '../utils/quoteFormat';
import { TOP_NINE_HALTED, TOP_NINE_MUTED_TITLE, TOP_NINE_TILE_TITLE } from './topNineConstants';
import { markLeft, markPhase, moveText, type TopNineMove } from './topNineMarks';
import type { TopNineRow } from './topNineSnapshot';
import { TopNineChart } from './TopNineChart';

function ago(ms: number): string {
  return `${Math.max(0, Math.floor(ms / 1000))}s ago`;
}

export interface TopNineTileProps {
  row: TopNineRow;
  move: TopNineMove | undefined;
  /** The board's minute in chart time (ET wall-clock seconds): where every tile's chart ends. */
  endTime: number | null;
  /** The list draws the LULD band (TOP_NINE_LULD_LISTS). */
  luld: boolean;
  now: number;
  opening: boolean;
  muted: boolean;
  onOpen: (symbol: string) => void;
  onMenu: (symbol: string, x: number, y: number) => void;
}

export const TopNineTile = forwardRef<HTMLDivElement, TopNineTileProps>(function TopNineTile(
  { row, move, endTime, luld, now, opening, muted, onOpen, onMenu },
  ref,
) {
  const phase = markPhase(move, now);
  const kind = phase === 'none' ? null : move?.kind ?? null;
  const cls = [
    'top-nine-tile',
    kind ? `is-${kind}` : '',
    phase === 'soft' ? 'is-soft' : '',
    opening ? 'is-opening' : '',
  ].filter(Boolean).join(' ');
  const tone = row.changePct == null ? '' : row.changePct >= 0 ? ' is-pos' : ' is-neg';
  return (
    <div
      ref={ref}
      className={cls}
      data-testid={`top-nine-tile-${row.symbol}`}
      data-rank={row.rank}
      data-mark={kind ?? 'none'}
      data-phase={phase}
      data-muted={muted ? 'true' : undefined}
      title={TOP_NINE_TILE_TITLE(row.symbol)}
      onDoubleClick={() => onOpen(row.symbol)}
      onContextMenu={(ev) => {
        ev.preventDefault();
        onMenu(row.symbol, ev.clientX, ev.clientY);
      }}
    >
      {phase === 'full' && move ? (
        <i className="top-nine-tile__timer" aria-hidden="true">
          <b style={{ transform: `scaleX(${markLeft(move, now).toFixed(3)})` }} />
        </i>
      ) : null}
      <div className="top-nine-tile__head">
        <span className="top-nine-tile__rank">{row.rank}</span>
        <div className="top-nine-tile__who">
          <div className="top-nine-tile__name">
            <TickerLink symbol={row.symbol} onOpen={onOpen} look="own" className="top-nine-tile__ticker" />
            {muted ? (
              <span
                className="top-nine-tile__muted"
                title={TOP_NINE_MUTED_TITLE(row.symbol)}
                data-testid={`top-nine-muted-${row.symbol}`}
              >
                <BellOff size={13} aria-hidden="true" />
              </span>
            ) : null}
            {phase === 'full' && move ? (
              <>
                <span className={`top-nine-pill top-nine-pill--${move.kind}`} data-testid={`top-nine-pill-${row.symbol}`}>
                  {move.kind === 'up' ? '▲ ' : move.kind === 'down' ? '▼ ' : ''}
                  {moveText(move)}
                </span>
                <span className="top-nine-tile__ago">{ago(now - move.at)}</span>
              </>
            ) : null}
            {row.halted ? <span className="top-nine-chip top-nine-chip--halt">{TOP_NINE_HALTED}</span> : null}
          </div>
          <div className="top-nine-tile__sub">
            Vol {fmtVolume(row.volume)} · Float {fmtVolume(row.float)}
          </div>
        </div>
        <span className={`top-nine-tile__chg${tone}`}>{fmtPct(row.changePct, '—')}</span>
      </div>
      <TopNineChart symbol={row.symbol} lastPrice={row.price} endTime={endTime} luld={luld} />
    </div>
  );
});
