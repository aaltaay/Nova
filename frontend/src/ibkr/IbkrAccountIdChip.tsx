/**
 * Header account-id chip: which account the desk trades. On Live it is the IBKR
 * account (U… live, DU… IBKR paper); on the practice venues it is Nova's own
 * NOVA-PAPER / NOVA-SIM (ADR 020). Cash / Margin says what kind of account;
 * this says which one. Hidden while disconnected -- an old id would be a lie.
 */
import {
  deskVenuePracticeAccountTooltip,
  isPracticeAccountId,
} from '../constantGroups/desk_venue';
import { GLOBAL_BAR_ACCOUNT_ID_ARIA, globalBarAccountIdTooltip } from '../constantGroups/global_bar';
import { useIbkrStatus } from './useIbkrStatus';

export function IbkrAccountIdChip() {
  const status = useIbkrStatus();
  const id = status.connected ? status.account_id ?? null : null;
  if (!id) return null;
  const practice = isPracticeAccountId(id);
  const kind = practice ? 'practice' : status.broker_account_kind ?? 'unknown';
  const others = (status.account_ids ?? []).filter(other => other !== id);
  return (
    <span
      className={`global-app-bar__account-id global-app-bar__account-id--${kind}`}
      title={
        practice
          ? deskVenuePracticeAccountTooltip(id)
          : globalBarAccountIdTooltip(id, kind, others)
      }
      aria-label={`${GLOBAL_BAR_ACCOUNT_ID_ARIA}: ${id}`}
      data-testid="global-bar-account-id"
      data-kind={kind}
    >
      {id}
    </span>
  );
}
