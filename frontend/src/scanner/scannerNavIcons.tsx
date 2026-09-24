/**
 * Compact stroke icons for the Webull-style scanner left rail.
 */
import type { ReactNode } from 'react';

const size = 22;

function Icon({ children }: { children: ReactNode }) {
  return (
    <svg
      className="scanner-side-nav__icon-svg"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      {children}
    </svg>
  );
}

const ICONS: Record<string, ReactNode> = {
  gappers: (
    <Icon>
      <path d="M4 14l4-4 3 3 6-7 3 2" />
      <path d="M4 20h16" />
    </Icon>
  ),
  gainers: (
    <Icon>
      <path d="M12 19V5" />
      <path d="M6 11l6-6 6 6" />
    </Icon>
  ),
  losers: (
    <Icon>
      <path d="M12 5v14" />
      <path d="M6 13l6 6 6-6" />
    </Icon>
  ),
  afterhours: (
    <Icon>
      <path d="M21 14.5A8.5 8.5 0 1112.5 4a7 7 0 008.5 10.5z" />
    </Icon>
  ),
  volume_boost: (
    <Icon>
      <path d="M4 18V9" />
      <path d="M10 18V5" />
      <path d="M16 18v-7" />
      <path d="M20 18V4" />
    </Icon>
  ),
  large_cap: (
    <Icon>
      <rect x="3" y="4" width="18" height="16" rx="2" />
      <path d="M7 15l3-4 3 2 4-6" />
    </Icon>
  ),
  earnings: (
    <Icon>
      <rect x="4" y="3" width="16" height="18" rx="2" />
      <path d="M8 8h8" />
      <path d="M8 12h8" />
      <path d="M8 16h5" />
    </Icon>
  ),
  nova_news: (
    <Icon>
      <rect x="3" y="4" width="18" height="16" rx="2" />
      <path d="M7 8h10" />
      <path d="M7 12h6" />
      <path d="M7 16h8" />
    </Icon>
  ),
  catalysts: (
    <Icon>
      <path d="M4 6h12" />
      <path d="M4 12h16" />
      <path d="M4 18h10" />
      <circle cx="19" cy="6" r="1.5" fill="currentColor" stroke="none" />
    </Icon>
  ),
  hod_momo: (
    <Icon>
      <path d="M12 3c2 4 2 6 0 9 3-1 5 1 5 4a5 5 0 11-10 0c0-2 1-3.5 2.5-4.5C8 9 9 6 12 3z" />
    </Icon>
  ),
  running_up: (
    <Icon>
      <path d="M4 17l5-5 3 3 7-8" />
      <path d="M14 7h5v5" />
    </Icon>
  ),
  // The operator's hand-picked Watch list: an eye.
  watch_list: (
    <Icon>
      <path d="M2 12s3.6-6.5 10-6.5S22 12 22 12s-3.6 6.5-10 6.5S2 12 2 12z" />
      <circle cx="12" cy="12" r="3" />
    </Icon>
  ),
  // Contenders (the ranked Five Pillars list, id `watchlist`): a podium.
  watchlist: (
    <Icon>
      <path d="M9 20V8h6v12" />
      <path d="M3 20v-7h6" />
      <path d="M15 20v-5h6v5" />
      <path d="M2 20h20" />
    </Icon>
  ),
  advise: (
    <Icon>
      <path d="M8 7h8" />
      <path d="M8 12h5" />
      <path d="M17 12v7l-2-1-2 1v-7" />
      <rect x="4" y="4" width="16" height="16" rx="2" />
    </Icon>
  ),
};

export function scannerNavIcon(moduleId: string): ReactNode {
  return ICONS[moduleId] ?? (
    <Icon>
      <circle cx="12" cy="12" r="7" />
    </Icon>
  );
}

export function formatScannerNavCount(count: number): string {
  if (count <= 0) return '';
  if (count > 99) return '99+';
  return String(count);
}
