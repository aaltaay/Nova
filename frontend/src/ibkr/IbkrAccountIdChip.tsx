/**
 * Header account-id chip: which IBKR account the desk is logged into (DU… paper,
 * U… live). Cash / Margin says what kind of account; this says which one.
 * Hidden while disconnected -- an old id would be a lie.
 */
import { GLOBAL_BAR_ACCOUNT_ID_ARIA, globalBarAccountIdTooltip } from '../constantGroups/global_bar';
import { useIbkrStatus } from './useIbkrStatus';

export function IbkrAccountIdChip() {
  const status = useIbkrStatus();
  const id = status.connected ? status.account_id ?? null : null;
  if (!id) return null;
  const kind = status.broker_account_kind ?? 'unknown';
  const others = (status.account_ids ?? []).filter(other => other !== id);
  return (
    <span
      className={`global-app-bar__account-id global-app-bar__account-id--${kind}`}
      title={globalBarAccountIdTooltip(id, kind, others)}
      aria-label={`${GLOBAL_BAR_ACCOUNT_ID_ARIA}: ${id}`}
      data-testid="global-bar-account-id"
      data-kind={kind}
    >
      {id}
    </span>
  );
}
