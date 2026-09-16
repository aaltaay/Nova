import { GLOBAL_BAR_ACCOUNT_TYPE_ARIA } from '../constantGroups/global_bar';
import { accountTypeChipView } from './accountTypeChip';
import type { IbkrAccountSummary } from './types';

interface Props {
  ibkrConnected: boolean;
  summary: IbkrAccountSummary | null;
}

export function IbkrAccountTypeChip({ ibkrConnected, summary }: Props) {
  const view = accountTypeChipView({ ibkrConnected, summary });
  if (!view) return null;
  return (
    <span
      className={`global-app-bar__account-type global-app-bar__account-type--${view.kind}`}
      title={view.tooltip}
      aria-label={`${GLOBAL_BAR_ACCOUNT_TYPE_ARIA}: ${view.label}`}
      data-testid="global-bar-account-type"
      data-kind={view.kind}
    >
      {view.label}
    </span>
  );
}
