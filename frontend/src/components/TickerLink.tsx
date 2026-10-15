/** A stock ticker anywhere on the desk is a shortcut to its Trader tab (operator ask, 2026-10-15: "make this a
 * shortcut for every ticker in the software ... all using a single source of truth").
 *
 * This is that one source: a click opens the Trader through the workspace's own `openStockView` -- the preview
 * tab, or the symbol's tab already open (ADR 011) -- with the same look and hover everywhere. Inside a clickable
 * row only the ticker's own click runs. A caller with its own open (a table that also selects the row, a page
 * handed its Trader door) passes `onOpen`; the button, look and hover stay these. With no workspace and no
 * `onOpen` (a part rendered on its own, in a test) the ticker is plain text: there is no Trader to open.
 * `components/tickerLinkCoverage.test.ts` fails on a ticker drawn as plain text anywhere else. */
import type { ReactNode } from 'react';
import { TICKER_OPEN_TRADER_TITLE } from '../constants';
import { tipProps } from '../ux/hoverTip';
import { useWorkspace } from '../workspace';

type OpenStockView = (symbol: string, opts?: { pin?: boolean; from?: string }) => void;

interface Props {
  symbol: string;
  /** The scanner list it was picked from, which the Focus rail follows. */
  from?: string;
  /** Land the tab beside the preview tab instead of replacing it. */
  pin?: boolean;
  /** Open it another way (still a Trader open): runs instead of the workspace's open. */
  onOpen?: (symbol: string) => void;
  /** What to draw; the symbol by default. */
  children?: ReactNode;
  /** Extra classes on the button (and on the plain text). */
  className?: string;
  /** 'own': the caller's class draws it, without the desk's link colour. */
  look?: 'link' | 'own';
  testId?: string;
}

/** The workspace's open, or null where no workspace is mounted. */
function useOpenStockView(): OpenStockView | null {
  try {
    return useWorkspace().openStockView ?? null;
  } catch {
    // No WorkspaceProvider above this part: there is no Trader to open, and the ticker says so by being plain text.
    return null;
  }
}

export function TickerLink({ symbol, from, pin, onOpen, children, className = '', look = 'link', testId }: Props) {
  const openStockView = useOpenStockView();
  const sym = symbol.trim().toUpperCase();
  const opts = from !== undefined || pin !== undefined ? { from, pin } : undefined;
  const open = onOpen ?? (openStockView ? (s: string) => (opts ? openStockView(s, opts) : openStockView(s)) : null);
  const shown = children ?? symbol;
  if (!open || !sym) return <span className={className || undefined} data-testid={testId}>{shown}</span>;
  const cls = ['ticker-link', look === 'link' ? 'symbol-btn' : '', className].filter(Boolean).join(' ');
  return (
    <button
      type="button"
      className={cls}
      data-testid={testId}
      {...tipProps(TICKER_OPEN_TRADER_TITLE, sym)}
      onClick={e => {
        e.stopPropagation();
        open(sym);
      }}
    >
      {shown}
    </button>
  );
}
