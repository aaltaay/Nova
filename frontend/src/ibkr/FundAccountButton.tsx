/**
 * GlobalAppBar shortcut to IBKR Client Portal (deposit lives there).
 * Nova never moves money -- this only reuses openIbkrClientPortal.
 */
import {
  GLOBAL_BAR_FUND_ACCOUNT_LABEL,
  GLOBAL_BAR_FUND_ACCOUNT_TITLE,
} from '../constants';
import { openIbkrClientPortal } from './openIbkrClientPortal';

export function FundAccountButton() {
  return (
    <button
      type="button"
      className="global-app-bar__fund"
      title={GLOBAL_BAR_FUND_ACCOUNT_TITLE}
      data-testid="global-bar-fund-account"
      onClick={() => {
        void openIbkrClientPortal();
      }}
    >
      {GLOBAL_BAR_FUND_ACCOUNT_LABEL}
    </button>
  );
}
