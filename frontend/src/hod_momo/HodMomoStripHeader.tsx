/**
 * Strip header line: HOD MOMO · N alerts since HH:MM · ● integrity ok ·
 * [HOD | Running Up] · feed · ⋯ · chevron. Clicking the bare header folds.
 */
import type { ReactNode } from 'react';
import { HodMomoDockModes } from './HodMomoDockModes';
import {
  HOD_MOMO_STRIP_FEED_LIVE,
  HOD_MOMO_STRIP_FEED_OFFLINE,
  HOD_MOMO_STRIP_FOLD_TITLE,
  HOD_MOMO_STRIP_INTEGRITY_LABEL,
  HOD_MOMO_STRIP_MORE_TITLE,
  HOD_MOMO_STRIP_TITLE,
  HOD_MOMO_STRIP_UNFOLD_TITLE,
} from './hodMomoStripConstants';
import type { HodDockMode } from './scannerDockModes';
import type { HodMomoIntegrityState } from './useHodMomoIntegrity';

type Props = {
  sinceLabel: string;
  integrity: HodMomoIntegrityState;
  connected: boolean;
  dockMode: HodDockMode;
  onSelectMode: (mode: HodDockMode) => void;
  hodCount: number;
  runningUpCount: number;
  collapsed: boolean;
  onToggleCollapsed: () => void;
  menuOpen: boolean;
  onToggleMenu: () => void;
  menu: ReactNode;
};

function integrityTitle(integrity: HodMomoIntegrityState): string {
  if (integrity.error) return `Integrity unreachable: ${integrity.error}`;
  const failed = (integrity.report?.checks ?? []).filter((c) => c.status !== 'pass');
  if (failed.length === 0) return 'HOD / scanner integrity checks pass';
  return failed.slice(0, 6).map((c) => `${c.id}: ${c.detail}`).join('\n');
}

export function HodMomoStripHeader({
  sinceLabel,
  integrity,
  connected,
  dockMode,
  onSelectMode,
  hodCount,
  runningUpCount,
  collapsed,
  onToggleCollapsed,
  menuOpen,
  onToggleMenu,
  menu,
}: Props) {
  return (
    <header
      className="hod-strip__head"
      onClick={(e) => {
        const el = e.target as HTMLElement;
        if (el.closest('button, [role="menu"], [role="tablist"]')) return;
        onToggleCollapsed();
      }}
    >
      <span className="hod-strip__title">{HOD_MOMO_STRIP_TITLE}</span>
      <span className="hod-strip__sep" aria-hidden="true">·</span>
      <span className="hod-strip__since" data-testid="hod-momo-strip-since">{sinceLabel}</span>
      <span className="hod-strip__sep" aria-hidden="true">·</span>
      <span
        className={`hod-strip__integrity is-${integrity.status}`}
        data-testid="hod-momo-strip-integrity"
        data-status={integrity.status}
        title={integrityTitle(integrity)}
      >
        <i className="hod-strip__dot" aria-hidden="true" />
        <span className="hod-strip__integrity-text">
          {HOD_MOMO_STRIP_INTEGRITY_LABEL[integrity.status] ?? integrity.status}
        </span>
      </span>
      <HodMomoDockModes
        dockMode={dockMode}
        onSelect={onSelectMode}
        hodCount={hodCount}
        runningUpCount={runningUpCount}
        rosterCounts={null}
      />
      <span
        className={`hod-strip__feed${connected ? ' is-live' : ''}`}
        title={connected ? 'HOD feed connected' : 'HOD feed disconnected'}
      >
        {connected ? HOD_MOMO_STRIP_FEED_LIVE : HOD_MOMO_STRIP_FEED_OFFLINE}
      </span>
      <span className="hod-strip__spacer" />
      <span className="hod-strip__menu-host">
        <button
          type="button"
          className={`hod-strip__more${menuOpen ? ' is-open' : ''}`}
          title={HOD_MOMO_STRIP_MORE_TITLE}
          aria-haspopup="menu"
          aria-expanded={menuOpen}
          data-testid="hod-momo-strip-more"
          onClick={(e) => {
            e.stopPropagation();
            onToggleMenu();
          }}
        >
          ⋯
        </button>
        {menuOpen ? menu : null}
      </span>
      <button
        type="button"
        className="hod-strip__chev"
        onClick={(e) => {
          e.stopPropagation();
          onToggleCollapsed();
        }}
        aria-expanded={!collapsed}
        data-testid="hod-momo-dock-toggle"
        title={collapsed ? HOD_MOMO_STRIP_UNFOLD_TITLE : HOD_MOMO_STRIP_FOLD_TITLE}
      >
        <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" className={collapsed ? 'is-folded' : undefined}>
          <path d="M6 9l6 6 6-6" />
        </svg>
      </button>
    </header>
  );
}
