/**
 * Board header: list title · filter chips · Saved: <name> ▾ · session line.
 * The session line leads with the history-date picker (Today (Live) ▾ --
 * Scanner-only, so it left the global bar in the 2026-09-22 redesign) and
 * the health chip stays in the global bar (not duplicated here).
 */
import { useEffect, useRef, useState } from 'react';
import { fmtHistoryDateShort } from '../components/globalAppBarScanner';
import { useScannerBarProps } from '../components/scannerBarStore';
import {
  SCANNER_CHIP_IDS,
  SCANNER_CHIP_LABEL,
  SCANNER_CHIP_TITLE,
  SCANNER_HISTORY_SAMPLE_LABEL,
  SCANNER_HISTORY_SELECT_ARIA,
  SCANNER_HISTORY_SELECT_TITLE,
  SCANNER_HISTORY_TODAY_LABEL,
  SCANNER_SAVED_DELETE_TITLE,
  SCANNER_SAVED_EMPTY,
  SCANNER_SAVED_LABEL,
  SCANNER_SAVED_MENU_TITLE,
  SCANNER_SAVED_PROMPT_MESSAGE,
  SCANNER_SAVED_PROMPT_TITLE,
  SCANNER_SAVED_SAVE_AS,
  SCANNER_SCANNED_MINUTES_MAX,
  SCANNER_SCANNED_SECONDS_MAX,
  SCANNER_SESSION_FEED_FAILED_TITLE,
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
  /** A scanner REST route failed (QA C31) -- stated on the board, not only in the console. */
  feedFailure?: string | null;
};

/** "45s" under 90 s, "12m" under 90 min, then "1h 05m" (QA V27 / C67: no raw 3130s). */
export function fmtScannedAgo(sec: number): string {
  const s = Math.max(0, Math.round(sec));
  if (s < SCANNER_SCANNED_SECONDS_MAX) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < SCANNER_SCANNED_MINUTES_MAX) return `${m}m`;
  return `${Math.floor(m / 60)}h ${String(m % 60).padStart(2, '0')}m`;
}

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

/** Today (Live) ▾ -- the same select the global bar used to carry, unchanged in behaviour. */
function HistoryDateSelect() {
  const bar = useScannerBarProps();
  if (!bar) return null;
  return (
    <>
      <select
        className={`history-select scanner-board__history${bar.historyDate ? ' history-select--active' : ''}`}
        value={bar.historyDate ?? ''}
        onChange={bar.onHistoryChange}
        title={SCANNER_HISTORY_SELECT_TITLE}
        aria-label={SCANNER_HISTORY_SELECT_ARIA}
        disabled={bar.sampleDataActive}
        data-testid="scanner-board-history"
      >
        <option value="">{bar.sampleDataActive ? SCANNER_HISTORY_SAMPLE_LABEL : SCANNER_HISTORY_TODAY_LABEL}</option>
        {!bar.sampleDataActive &&
          bar.historyDates.map((d) => (
            <option key={d} value={d}>
              {fmtHistoryDateShort(d)}
            </option>
          ))}
      </select>
      <span className="scanner-board__sep" aria-hidden="true">·</span>
    </>
  );
}

export function ScannerBoardHeader({ title, filters, scannedAgoSec, feedFailure = null }: Props) {
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
        {/* Snapshots exist for scanner lists only -- not on Bots / Watchlist (QA V30). */}
        {filters ? <HistoryDateSelect /> : null}
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
                : <>{SCANNER_SESSION_SCANNED_PREFIX} <b>{fmtScannedAgo(scannedAgoSec)}</b> {SCANNER_SESSION_SCANNED_SUFFIX}</>}
            </span>
          </>
        ) : null}
        {feedFailure ? (
          <>
            <span className="scanner-board__sep" aria-hidden="true">·</span>
            <span
              className="scanner-board__feed-failed"
              role="alert"
              title={SCANNER_SESSION_FEED_FAILED_TITLE}
              data-testid="scanner-board-feed-failed"
            >
              {feedFailure}
            </span>
          </>
        ) : null}
      </span>
    </header>
  );
}
