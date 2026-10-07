/**
 * The Short / Cover hotkeys' own fields (ADR 048), for both Nova Action editors: a Short's size, its price
 * offset from the bid or the ask (signed: under SSR a short sells above the bid) and its own buy stop, which
 * starts at the venue's Settings > Trade offset; a limit Cover's offset over the ask.
 */
import {
  NOVA_ACTION_DEFAULT_OFFSET_DOLLARS,
  NOVA_ACTION_DEFAULT_SHARES,
  NOVA_ACTION_DEFAULT_SHORT_OFFSET_DOLLARS,
} from '../constants';
import {
  SHORT_HOTKEY_COVER_ALL_NOTE,
  SHORT_HOTKEY_OFFSET_HINT,
  SHORT_HOTKEY_STOP_LABEL,
} from '../constantGroups/short_ticket';
import type { NovaActionRecord } from './novaActionTypes';

interface Props {
  action: NovaActionRecord;
  /** The editor's own field class (`hotkey-editor-field`, `hk-field`). */
  fieldClass: string;
  /** The venue's Settings > Trade short buy stop offset: what an unset hotkey uses. */
  venueStopOffset: number;
  onChange: (next: NovaActionRecord) => void;
}

export function isShortHotkeyKind(kind: NovaActionRecord['kind']): boolean {
  return kind === 'short_limit_bid_offset' || kind === 'short_limit_ask_offset'
    || kind === 'cover_limit_ask_offset' || kind === 'cover_pos';
}

export function ShortActionFields({ action, fieldClass, venueStopOffset, onChange }: Props) {
  const set = (patch: Partial<NovaActionRecord['params']>) => onChange({ ...action, params: { ...action.params, ...patch } });
  const short = action.kind === 'short_limit_bid_offset' || action.kind === 'short_limit_ask_offset';
  if (action.kind === 'cover_pos') {
    return <p className="hk-hint" data-testid="short-hotkey-cover-all-note">{SHORT_HOTKEY_COVER_ALL_NOTE}</p>;
  }
  const defaultOffset = action.kind === 'short_limit_bid_offset'
    ? NOVA_ACTION_DEFAULT_SHORT_OFFSET_DOLLARS
    : action.kind === 'short_limit_ask_offset' ? -NOVA_ACTION_DEFAULT_SHORT_OFFSET_DOLLARS : NOVA_ACTION_DEFAULT_OFFSET_DOLLARS;
  return (
    <>
      {short && (
        <label className={fieldClass}>
          <span>Shares</span>
          <input
            type="number"
            value={action.params.shares ?? NOVA_ACTION_DEFAULT_SHARES}
            onChange={(e) => set({ shares: Number(e.target.value) })}
            data-testid="short-hotkey-shares"
          />
        </label>
      )}
      <label className={fieldClass}>
        <span>Offset ($)</span>
        <input
          type="number"
          step="0.01"
          value={action.params.offsetDollars ?? defaultOffset}
          onChange={(e) => set({ offsetDollars: Number(e.target.value) })}
          title={short ? SHORT_HOTKEY_OFFSET_HINT : undefined}
          data-testid="short-hotkey-offset"
        />
      </label>
      {short && (
        <label className={fieldClass}>
          <span>{SHORT_HOTKEY_STOP_LABEL}</span>
          <input
            type="number"
            step="0.01"
            min="0.01"
            value={action.params.stopOffsetDollars ?? venueStopOffset}
            onChange={(e) => set({ stopOffsetDollars: Number(e.target.value) })}
            data-testid="short-hotkey-stop-offset"
          />
        </label>
      )}
    </>
  );
}
