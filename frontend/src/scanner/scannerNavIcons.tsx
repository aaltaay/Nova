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
  watchlist: (
    <Icon>
      <path d="M12 20s-7-4.5-7-10a4 4 0 017-2.5A4 4 0 0119 10c0 5.5-7 10-7 10z" />
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
