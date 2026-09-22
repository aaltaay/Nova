/**
 * Stroke icons for the nav rail's top-level items (from the approved prototype).
 * Scanner children reuse scannerNavIcon() so the lists keep their icons.
 */
import type { ReactNode } from 'react';

function Icon({ children }: { children: ReactNode }) {
  return (
    <svg
      className="nav-rail__icon-svg"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      {children}
    </svg>
  );
}

export type NavRailIconId =
  | 'desk'
  | 'trader'
  | 'scanner'
  | 'account'
  | 'bots'
  | 'records'
  | 'settings';

const ICONS: Record<NavRailIconId, ReactNode> = {
  desk: (
    <Icon>
      <rect x="3" y="3" width="8" height="8" rx="1.5" />
      <rect x="13" y="3" width="8" height="8" rx="1.5" />
      <rect x="3" y="13" width="8" height="8" rx="1.5" />
      <rect x="13" y="13" width="8" height="8" rx="1.5" />
    </Icon>
  ),
  trader: (
    <Icon>
      <path d="M7 4v4M7 16v4M7 8h-2v8h2zM7 8h2v8H7" />
      <path d="M17 3v3M17 18v3M17 6h-2v12h2zM17 6h2v12h-2" />
      <path d="M12 10v4" />
    </Icon>
  ),
  scanner: (
    <Icon>
      <circle cx="11" cy="11" r="7" />
      <path d="M16.5 16.5 21 21" />
      <path d="M8 11h6M11 8v6" />
    </Icon>
  ),
  account: (
    <Icon>
      <rect x="3" y="6" width="18" height="13" rx="2" />
      <path d="M3 10h18" />
      <path d="M16 15h2" />
    </Icon>
  ),
  bots: (
    <Icon>
      <rect x="4" y="8" width="16" height="11" rx="2" />
      <path d="M12 8V4M9 4h6" />
      <circle cx="9" cy="13.5" r="1" />
      <circle cx="15" cy="13.5" r="1" />
      <path d="M9 17h6" />
    </Icon>
  ),
  records: (
    <Icon>
      <circle cx="12" cy="12" r="8.5" />
      <circle cx="12" cy="12" r="3.5" fill="currentColor" stroke="none" />
    </Icon>
  ),
  settings: (
    <Icon>
      <circle cx="12" cy="12" r="3" />
      <path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M4.9 19.1 7 17M17 7l2.1-2.1" />
    </Icon>
  ),
};

export function navRailIcon(id: NavRailIconId): ReactNode {
  return ICONS[id];
}

export function NavRailChevron() {
  return (
    <svg
      className="nav-rail__chev-svg"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="M6 9l6 6 6-6" />
    </svg>
  );
}
