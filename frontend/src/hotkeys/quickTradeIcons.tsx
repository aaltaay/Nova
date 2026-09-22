/** Inline glyphs for the quick-trade row (strokes from `ux/mockup-trader.html`). */
import type { NovaActionKind } from '../constants';

const ICON_PATHS: Record<NovaActionKind, string> = {
  cancel_symbol: 'M6 6l12 12M18 6L6 18',
  cancel_and_exit: 'M4 6h16M4 12h16M4 18h10M17 15l3 3 3-3',
  cancel_all_orders: 'M4 4l6 6M10 4L4 10M14 14l6 6M20 14l-6 6',
  exit_pos: 'M4 6h16M4 12h16M4 18h10M17 15l3 3 3-3',
  exit_pos_pct: 'M12 4a8 8 0 1 0 0 16 8 8 0 0 0 0-16zm0 0v16',
  buy_market: 'M13 2L4 14h7l-1 8 9-12h-7z',
  buy_limit_ask_offset: 'M12 19V5M5 12l7-7 7 7',
  sell_limit_bid_offset: 'M12 5v14M5 12l7 7 7-7',
  sell_limit_ask_offset: 'M12 5v14M5 12l7 7 7-7',
  sell_pos_pct_ask: 'M12 5v14M5 12l7 7 7-7',
  sell_pos_pct_bid_offset: 'M12 5v14M5 12l7 7 7-7',
};

const GEAR_PATH =
  'M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12M20 18h0M15 4a2 2 0 1 0 0 4 2 2 0 0 0 0-4zM9 10a2 2 0 1 0 0 4 2 2 0 0 0 0-4zM17 16a2 2 0 1 0 0 4 2 2 0 0 0 0-4z';

function Glyph({ d }: { d: string }) {
  return (
    <svg
      width="15"
      height="15"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={d} />
    </svg>
  );
}

export function QuickTradeIcon({ kind }: { kind: NovaActionKind }) {
  return <Glyph d={ICON_PATHS[kind]} />;
}

export function QuickTradeGearIcon() {
  return <Glyph d={GEAR_PATH} />;
}
