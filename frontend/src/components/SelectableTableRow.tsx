/** Table body row: click (or Enter/Space) opens Trader and replaces the
 * active tab (ADR 011). Double-click has no special action here.
 *
 * When `openOnRowClick` is false (tables that also render a blue
 * `SymbolSelectButton`), the row body only selects the symbol -- it does
 * not open Trader. The ticker button is the one gesture that opens Trader.
 * This is a spatial split (row vs ticker), not the click-vs-double-click
 * split ADR 011 rejected. */
import type { CSSProperties, KeyboardEvent, MouseEvent, ReactNode } from 'react';
import { openBotSymbolMenu } from '../bot/botSymbolMenuStore';
import { ROW_SELECT_QUOTE_TITLE, TICKER_OPEN_TRADER_TITLE } from '../constants';

interface Props {
  symbol: string;
  selected: boolean;
  onSelect: (symbol: string) => void;
  onOpenTrading: (symbol: string) => void;
  children: ReactNode;
  className?: string;
  style?: CSSProperties;
  /** Optional row tip prepended before the row hint. */
  hintPrefix?: string;
  /** Marks extremely recent closed fills/cancels for tests + CSS. */
  dataRecent?: boolean;
  /** False when a sibling `SymbolSelectButton` owns opening Trader; the row
   * body then only calls `onSelect`. Defaults to true for rows with no
   * ticker button (Positions, Orders, Journal, ...). */
  openOnRowClick?: boolean;
  /** Ticker lists: right-click opens the symbol menu (watch list, Record, bot allowlist). */
  symbolMenu?: boolean;
  /** False where the cells explain themselves (ux/hoverTip.ts): the row's own native
   * tooltip would stack on top of theirs. Defaults to true. */
  rowTitle?: boolean;
}

export function SelectableTableRow({
  symbol,
  selected,
  onSelect,
  onOpenTrading,
  children,
  className = '',
  style,
  hintPrefix,
  dataRecent = false,
  openOnRowClick = true,
  symbolMenu = false,
  rowTitle = true,
}: Props) {
  function openRow() {
    onSelect(symbol);
    if (openOnRowClick) onOpenTrading(symbol);
  }

  function onKeyDown(e: KeyboardEvent<HTMLTableRowElement>) {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      openRow();
    }
  }

  const baseTitle = openOnRowClick ? TICKER_OPEN_TRADER_TITLE : ROW_SELECT_QUOTE_TITLE;
  const title = hintPrefix ? `${hintPrefix} · ${baseTitle}` : baseTitle;

  return (
    <tr
      className={`selectable-row${selected ? ' row-selected' : ''}${className ? ` ${className}` : ''}`}
      style={style}
      onClick={openRow}
      onContextMenu={
        symbolMenu
          ? (event: MouseEvent<HTMLTableRowElement>) => {
              event.preventDefault();
              openBotSymbolMenu(symbol, event.clientX, event.clientY);
            }
          : undefined
      }
      onKeyDown={onKeyDown}
      tabIndex={0}
      aria-selected={selected}
      title={rowTitle ? title : undefined}
      data-recent={dataRecent ? '1' : undefined}
    >
      {children}
    </tr>
  );
}
