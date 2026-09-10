import { IBKR_CLIENT_PORTAL_URL } from '../constants';

export async function openIbkrClientPortal(): Promise<void> {
  if (window.novaDesktop?.openExternal) {
    await window.novaDesktop.openExternal(IBKR_CLIENT_PORTAL_URL);
    return;
  }
  window.open(
    IBKR_CLIENT_PORTAL_URL,
    '_blank',
    'noopener,noreferrer',
  );
}
