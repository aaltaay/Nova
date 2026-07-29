/** Shortability chip for Level 2 header (Phase K4 / ADR 009). */
import type { IbkrListingFlags } from '../types/ticker';
import {
  SHORTABILITY_CHIP_TOOLTIP,
  SHORTABILITY_LABEL,
  SHORTABILITY_STATE_LABELS,
} from '../constantGroups/shortability';

interface Props {
  ibkr: IbkrListingFlags | null | undefined;
}

/** Prefer Phase K `state`; fall back to legacy listing_flags `short_type`. */
export function resolveShortabilityState(
  ibkr: IbkrListingFlags | null | undefined,
): string {
  if (ibkr?.state) return String(ibkr.state);
  const legacy = (ibkr?.short_type || '').toLowerCase();
  if (legacy === 'available') return 'shortable_est';
  if (legacy === 'limited') return 'thin';
  if (legacy === 'hard_to_borrow') return 'htb_likely';
  return 'unknown';
}

function stateClass(state: string | undefined, stale: boolean | undefined): string {
  if (stale || !state || state === 'unknown') return 'sv-shortability-chip--unknown';
  if (state === 'shortable_est') return 'sv-shortability-chip--ok';
  if (state === 'thin') return 'sv-shortability-chip--thin';
  if (state === 'htb_likely') return 'sv-shortability-chip--htb';
  return 'sv-shortability-chip--unknown';
}

export function ShortabilityChip({ ibkr }: Props) {
  const state = resolveShortabilityState(ibkr);
  const stale = Boolean(ibkr?.stale);
  const shares = ibkr?.shortable_shares;
  const label = stale
    ? 'Stale'
    : (SHORTABILITY_STATE_LABELS[state] ?? SHORTABILITY_STATE_LABELS.unknown);
  const sharesText =
    shares != null && Number.isFinite(shares)
      ? ` · ~${Math.round(shares).toLocaleString('en-US')}`
      : '';
  const title =
    ibkr?.short_type_detail?.trim() ||
    SHORTABILITY_CHIP_TOOLTIP;

  return (
    <span
      className={`sv-shortability-chip ${stateClass(state, stale)}`}
      title={title}
      data-testid="shortability-chip"
      data-state={stale ? 'stale' : state}
    >
      <span className="sv-shortability-chip__label">{SHORTABILITY_LABEL}</span>
      <span className="sv-shortability-chip__value">
        {label}
        {sharesText}
      </span>
    </span>
  );
}
