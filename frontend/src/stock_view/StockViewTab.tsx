/**
 * One slim symbol tab: REC dot · SYMBOL · signed gap · catalyst chip, with
 * pop-out / dock / close as hover icons. The active tab carries the full chip;
 * inactive tabs collapse it to its first letter (full name as tooltip) so the
 * row holds three tabs beside the Sim scrubber. Gap and chip are omitted when
 * the scanner has no row for the symbol -- never 0.00, never a guess.
 */
import { ArrowLeftToLine, ExternalLink, Pin, PinOff, X } from 'lucide-react';
import type { RefObject } from 'react';
import {
  TRADER_TAB_PIN_ARIA,
  TRADER_TAB_PIN_TITLE,
  TRADER_TAB_PREVIEW_TITLE,
  TRADER_TAB_UNPIN_ARIA,
  TRADER_TAB_UNPIN_TITLE,
} from '../constantGroups/trader_view';
import {
  TRADER_TAB_CLOSE_ARIA,
  TRADER_TAB_CLOSE_RECORDING_TITLE,
  TRADER_TAB_DOCK_ARIA,
  TRADER_TAB_DOCK_TITLE,
  TRADER_TAB_EXTRACT_ARIA,
  TRADER_TAB_EXTRACT_TITLE,
  TRADER_TAB_LABEL_TITLE,
  TRADER_TAB_LABEL_TITLE_FLOAT,
  TRADER_TAB_RECORDING_TITLE,
  TRADER_TAB_SUSPENDED_TITLE,
} from '../constants';
import { TRADER_TAB_GAP_TITLE } from '../constantGroups/trader_view';
import { catalystInitial, formatSignedPct, pctTone, type TabContext } from './tabContext';

export interface StockViewTabProps {
  label: string;
  isActive: boolean;
  isDraft: boolean;
  suspended: boolean;
  recording: boolean;
  /** ADR 011 preview tabs: an unpinned symbol is replaced by the next ticker opened. */
  pinned: boolean;
  context: TabContext | null;
  showDock: boolean;
  showExtract: boolean;
  /** Tooltip naming how this workspace's tabs move, when they cannot drag (the sample desk, #449). */
  moveTitle?: string;
  /** Why Dock cannot move this tab back; the button stays, locked, saying so. */
  dockWhy?: string | null;
  /** Why this tab cannot pop out; the button stays, locked, saying so. */
  extractWhy?: string | null;
  editing: boolean;
  draft: string;
  inputRef: RefObject<HTMLInputElement | null>;
  onDraftChange: (value: string) => void;
  onCommitEdit: () => void;
  onCancelEdit: () => void;
  onActivate: () => void;
  onExtract: () => void;
  onDock?: () => void;
  onTogglePin?: () => void;
  onClose: () => void;
}

export function StockViewTab({
  label, isActive, isDraft, suspended, recording, pinned, context, showDock, showExtract,
  moveTitle, dockWhy = null, extractWhy = null, editing, draft, inputRef, onDraftChange, onCommitEdit, onCancelEdit,
  onActivate, onExtract, onDock, onTogglePin, onClose,
}: StockViewTabProps) {
  const gap = context ? formatSignedPct(context.gapPct) : '';
  const chip = context?.catalyst ?? null;
  const chipTitle = context?.headline ? `${chip} · ${context.headline}` : chip ?? undefined;
  const labelTitle = isDraft
    ? 'Type a ticker, then Enter'
    : suspended
      ? TRADER_TAB_SUSPENDED_TITLE
      : !pinned
        ? TRADER_TAB_PREVIEW_TITLE
        : moveTitle ?? (showExtract ? TRADER_TAB_LABEL_TITLE : TRADER_TAB_LABEL_TITLE_FLOAT);
  return (
    <>
      {recording && !isDraft && (
        <span className="sv-tab__rec" title={TRADER_TAB_RECORDING_TITLE} data-testid={`sv-tab-rec-${label}`} aria-label={TRADER_TAB_RECORDING_TITLE} />
      )}
      {editing ? (
        <input
          ref={inputRef}
          className="sv-tab__input"
          value={draft}
          aria-label="Edit ticker"
          spellCheck={false}
          onChange={e => onDraftChange(e.target.value.toUpperCase())}
          onBlur={onCommitEdit}
          onKeyDown={e => {
            if (e.key === 'Enter') { e.preventDefault(); onCommitEdit(); }
            else if (e.key === 'Escape') { e.preventDefault(); onCancelEdit(); }
          }}
        />
      ) : (
        <button
          type="button"
          className="sv-tab__label"
          onClick={onActivate}
          onDoubleClick={e => { e.preventDefault(); if (!isDraft && showExtract && !extractWhy) onExtract(); }}
          title={labelTitle}
        >
          <span className="sv-tab__symbol">{label}</span>
          {gap && (
            <span
              className={`sv-tab__gap sv-tab__gap--${pctTone(context?.gapPct)}`}
              data-testid={`sv-tab-gap-${label}`}
              title={TRADER_TAB_GAP_TITLE}
            >
              {gap}
            </span>
          )}
          {chip && (
            <span
              className={`sv-tab__chip${isActive ? '' : ' sv-tab__chip--icon'}`}
              title={chipTitle}
              aria-label={chipTitle}
              data-testid={`sv-tab-chip-${label}`}
            >
              {isActive ? chip : catalystInitial(chip)}
            </span>
          )}
        </button>
      )}
      {!isDraft && (
        <span className="sv-tab__hover">
          {onTogglePin && (
            <button
              type="button"
              className={`sv-tab__pin${pinned ? ' sv-tab__pin--on' : ''}`}
              aria-label={`${pinned ? TRADER_TAB_UNPIN_ARIA : TRADER_TAB_PIN_ARIA} (${label})`}
              aria-pressed={pinned}
              title={pinned ? TRADER_TAB_UNPIN_TITLE : TRADER_TAB_PIN_TITLE}
              data-testid={`sv-tab-pin-${label}`}
              onClick={e => { e.stopPropagation(); onTogglePin(); }}
            >
              {pinned ? <PinOff size={12} aria-hidden="true" /> : <Pin size={12} aria-hidden="true" />}
            </button>
          )}
          {showDock && onDock && (
            <button type="button" className="sv-tab__dock" aria-label={`${TRADER_TAB_DOCK_ARIA} (${label})`}
              title={dockWhy ? '' : TRADER_TAB_DOCK_TITLE} data-testid={`sv-tab-dock-${label}`}
              disabled={Boolean(dockWhy)} data-why={dockWhy ?? undefined}
              onClick={e => { e.stopPropagation(); if (!dockWhy) onDock(); }}>
              <ArrowLeftToLine size={12} aria-hidden="true" />
            </button>
          )}
          {showExtract && (
            <button type="button" className="sv-tab__extract" aria-label={`${TRADER_TAB_EXTRACT_ARIA} (${label})`}
              title={extractWhy ? '' : TRADER_TAB_EXTRACT_TITLE} data-testid={`sv-tab-extract-${label}`}
              disabled={Boolean(extractWhy)} data-why={extractWhy ?? undefined}
              onClick={e => { e.stopPropagation(); if (!extractWhy) onExtract(); }}>
              <ExternalLink size={12} aria-hidden="true" />
            </button>
          )}
          {/* Locked while recording: the reason rides data-why, and title '' keeps the strip's own title off it. */}
          <button
            type="button"
            className="sv-tab__close"
            aria-label={recording ? `Recording ${label} — stop recording before close` : `${TRADER_TAB_CLOSE_ARIA} ${label}`}
            disabled={recording}
            data-why={recording ? TRADER_TAB_CLOSE_RECORDING_TITLE : undefined}
            title={recording ? '' : `${TRADER_TAB_CLOSE_ARIA} ${label}`}
            data-testid={`sv-tab-close-${label}`}
            onClick={e => {
              e.stopPropagation();
              if (recording) { e.preventDefault(); return; }
              if (editing) onCancelEdit(); else onClose();
            }}
          >
            <X size={12} aria-hidden="true" />
          </button>
        </span>
      )}
      {isDraft && (
        <button type="button" className="sv-tab__close" aria-label={`${TRADER_TAB_CLOSE_ARIA} ${label}`}
          data-testid={`sv-tab-close-${label}`}
          onClick={e => { e.stopPropagation(); if (editing) onCancelEdit(); else onClose(); }}>
          <X size={12} aria-hidden="true" />
        </button>
      )}
    </>
  );
}
