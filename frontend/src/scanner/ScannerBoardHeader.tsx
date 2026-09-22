/**
 * Board header: list title · filter chips · Saved: <name> ▾ · session line.
 * The health chip stays in the global bar (not duplicated here).
 */
import { useEffect, useRef, useState } from 'react';
import {
  SCANNER_CHIP_IDS,
  SCANNER_CHIP_LABEL,
  SCANNER_CHIP_TITLE,
  SCANNER_SAVED_DELETE_TITLE,
  SCANNER_SAVED_EMPTY,
  SCANNER_SAVED_LABEL,
  SCANNER_SAVED_MENU_TITLE,
  SCANNER_SAVED_PROMPT_MESSAGE,
  SCANNER_SAVED_PROMPT_TITLE,
  SCANNER_SAVED_SAVE_AS,
  SCANNER_SESSION_NOT_SCANNED,
  SCANNER_SESSION_SCANNED_PREFIX,
  SCANNER_SESSION_SCANNED_SUFFIX,
  SCANNER_SESSION_TITLE,
} from '../constantGroups/scanner_board';
import { promptApp } from '../ux';
import { isChipAvailable } from './boardFilters';
import { useSessionCountdown } from './sessionCountdown';
import type { BoardFilters } from './useBoardFilters';

type Props = {
  title: string;
  /** Chips apply to scanner-row lists only; other tabs show title + session line. */
  filters: BoardFilters | null;
  /** Seconds since the active list's last scan; null when it never scanned;
   * undefined for a list that is not scanned at all (segment omitted). */
  scannedAgoSec: number | null | undefined;
};

function SavedSetsMenu({ filters, onClose }: { filters: BoardFilters; onClose: () => void }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    };
    window.addEventListener('keydown', onKey);
    window.addEventListener('mousedown', onDown);
    return () => {
      window.removeEventListener('keydown', onKey);
      window.removeEventListener('mousedown', onDown);
    };
  }, [onClose]);

  const saveAs = async () => {
    const name = await promptApp({ title: SCANNER_SAVED_PROMPT_TITLE, message: SCANNER_SAVED_PROMPT_MESSAGE });
    if (name && name.trim()) filters.saveCurrentAs(name);
    onClose();
  };

  return (
    <div ref={ref} className="scanner-board__saved-menu" role="menu" aria-label={SCANNER_SAVED_MENU_TITLE} data-testid="scanner-board-saved-menu">
      {filters.sets.length === 0 ? (
        <div className="scanner-board__saved-empty">{SCANNER_SAVED_EMPTY}</div>
      ) : (
        filters.sets.map((set) => (
          <div key={set.name} className="scanner-board__saved-row">
            <button
              type="button"
              role="menuitem"
              className={`scanner-board__saved-item${filters.activeSetName === set.name ? ' is-active' : ''}`}
              title={set.chips.map((id) => SCANNER_CHIP_LABEL[id]).join(' · ') || '(no chips)'}
              onClick={() => { filters.applySet(set.name); onClose(); }}
              data-testid="scanner-board-saved-item"
            >
              {set.name}
            </button>
            <button
              type="button"
              className="scanner-board__saved-forget"
              title={SCANNER_SAVED_DELETE_TITLE}
              aria-label={`${SCANNER_SAVED_DELETE_TITLE}: ${set.name}`}
              onClick={() => filters.forgetSet(set.name)}
            >
              ×
            </button>
          </div>
        ))
      )}
      <button type="button" role="menuitem" className="scanner-board__saved-item scanner-board__saved-save" onClick={() => void saveAs()} data-testid="scanner-board-saved-save">
        {SCANNER_SAVED_SAVE_AS}
      </button>
    </div>
  );
}

export function ScannerBoardHeader({ title, filters, scannedAgoSec }: Props) {
  const session = useSessionCountdown();
  const [savedOpen, setSavedOpen] = useState(false);

  return (
    <header className="scanner-board__head" data-testid="scanner-board-header">
      <span className="scanner-board__title" data-testid="selected-scanner-title">{title}</span>
      {filters ? (
        <>
          <span className="scanner-board__vdiv" aria-hidden="true" />
          <div className="scanner-board__chips" role="group" aria-label="Board filters">
            {SCANNER_CHIP_IDS.map((id) => {
              const available = isChipAvailable(id);
              const on = filters.active.has(id);
              return (
                <button
                  key={id}
                  type="button"
                  className={`scanner-board__chip${on ? ' is-on' : ''}${available ? '' : ' is-unavailable'}`}
                  aria-pressed={on}
                  aria-disabled={!available}
                  title={SCANNER_CHIP_TITLE[id]}
                  data-testid={`scanner-chip-${id}`}
                  onClick={() => filters.toggle(id)}
                >
                  {SCANNER_CHIP_LABEL[id]}
                </button>
              );
            })}
            <span className="scanner-board__saved-host">
              <button
                type="button"
                className={`scanner-board__chip scanner-board__saved${savedOpen ? ' is-open' : ''}`}
                aria-haspopup="menu"
                aria-expanded={savedOpen}
                data-testid="scanner-board-saved"
                onClick={() => setSavedOpen((v) => !v)}
              >
                <i>{SCANNER_SAVED_LABEL}</i> {filters.activeSetName} <span className="scanner-board__caret">▾</span>
              </button>
              {savedOpen ? <SavedSetsMenu filters={filters} onClose={() => setSavedOpen(false)} /> : null}
            </span>
          </div>
        </>
      ) : null}
      <span className="scanner-board__session" title={SCANNER_SESSION_TITLE} data-testid="scanner-board-session">
        <span>{session.dateLabel}</span>
        <span className="scanner-board__sep" aria-hidden="true">·</span>
        <span data-testid="scanner-board-phase">
          {session.phaseLabel}
          {session.countdown ? <b className="scanner-board__cd">{session.countdown}</b> : null}
        </span>
        {scannedAgoSec !== undefined ? (
          <>
            <span className="scanner-board__sep" aria-hidden="true">·</span>
            <span data-testid="scanner-board-scanned">
              {scannedAgoSec === null
                ? SCANNER_SESSION_NOT_SCANNED
                : <>{SCANNER_SESSION_SCANNED_PREFIX} <b>{Math.max(0, Math.round(scannedAgoSec))}s</b> {SCANNER_SESSION_SCANNED_SUFFIX}</>}
            </span>
          </>
        ) : null}
      </span>
    </header>
  );
}
