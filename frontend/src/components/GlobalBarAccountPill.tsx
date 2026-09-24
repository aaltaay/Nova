/**
 * Header account pill -- "Individual Margin (U1234567)" -- and the menu under
 * it: every managed account on the login, the active one marked. Information
 * only: Nova cannot switch accounts (that happens in IB Gateway / TWS), and on
 * the practice venues Nova's ledger is the only account. The view model
 * (headerAccountPill.ts) is null while disconnected, so nothing renders then.
 */
import {
  GLOBAL_BAR_ACCOUNT_PILL_ACTIVE_MARK,
  GLOBAL_BAR_ACCOUNT_PILL_ARIA,
  GLOBAL_BAR_ACCOUNT_PILL_MENU_LABEL,
} from '../constantGroups/global_bar';
import type { HeaderAccountPillView } from './headerAccountPill';

interface ButtonProps {
  view: HeaderAccountPillView;
  open: boolean;
  menuId: string;
  onToggle: () => void;
  onHover: () => void;
}

export function AccountPillButton({ view, open, menuId, onToggle, onHover }: ButtonProps) {
  return (
    <button
      type="button"
      className={`global-app-bar__metric-btn global-app-bar__account-pill global-app-bar__account-pill--${view.kind}`}
      title={view.tooltip}
      aria-label={`${GLOBAL_BAR_ACCOUNT_PILL_ARIA}: ${view.label}`}
      aria-expanded={open}
      aria-controls={menuId}
      data-testid="global-bar-account-pill"
      data-kind={view.kind}
      data-account-id={view.id ?? ''}
      onClick={onToggle}
      onMouseEnter={onHover}
    >
      <span className="global-app-bar__account-pill-label">{view.label}</span>
      <span className="global-app-bar__caret" aria-hidden>
        {open ? '▴' : '▾'}
      </span>
    </button>
  );
}

export function AccountPillMenu({ view }: { view: HeaderAccountPillView }) {
  return (
    <div
      className="global-app-bar__card global-app-bar__pill-menu"
      role="menu"
      aria-label={GLOBAL_BAR_ACCOUNT_PILL_MENU_LABEL}
      data-testid="global-bar-account-pill-menu"
    >
      {view.accounts.map((account) => (
        <div
          key={account.id}
          className={`global-app-bar__card-row${account.active ? ' is-active' : ''}`}
          role="menuitem"
          aria-disabled
          data-why={view.note}
          aria-current={account.active ? 'true' : undefined}
          data-testid="global-bar-account-pill-item"
          data-account-id={account.id}
        >
          <span>{account.id}</span>
          <span>{account.active ? GLOBAL_BAR_ACCOUNT_PILL_ACTIVE_MARK : ''}</span>
        </div>
      ))}
      <div className="global-app-bar__menu-divider" aria-hidden />
      <p className="global-app-bar__card-note" data-testid="global-bar-account-pill-tooltip">
        {view.tooltip}
      </p>
      <p className="global-app-bar__card-note">{view.note}</p>
    </div>
  );
}
