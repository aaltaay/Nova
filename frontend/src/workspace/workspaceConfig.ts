/**
 * Pure helpers for WorkspaceContext /api/config payload handling.
 * Kept free of React so unit tests need no DOM.
 */
import { DATA_FEED_DEFAULT, DISCOVERY_PROVIDER_DEFAULT } from '../constants';

export type WorkspaceConfigSlice = {
  discoveryProvider: string;
  alpacaFeed: string;
  /** ADR 008 — when true, UI drops IBKR structural REST polls. */
  scannerPersistentAuthoritative: boolean;
};

export const WORKSPACE_CONFIG_DEFAULTS: WorkspaceConfigSlice = {
  discoveryProvider: DISCOVERY_PROVIDER_DEFAULT,
  alpacaFeed: DATA_FEED_DEFAULT,
  scannerPersistentAuthoritative: false,
};

/** Map a GET /api/config JSON body into the workspace discovery/feed slice. */
export function parseWorkspaceConfig(data: unknown): WorkspaceConfigSlice {
  if (!data || typeof data !== 'object') {
    return { ...WORKSPACE_CONFIG_DEFAULTS };
  }
  const row = data as Record<string, unknown>;
  // Product lock: scanner discovery is always IBKR (ignore stale alpaca payloads).
  const discoveryProvider = DISCOVERY_PROVIDER_DEFAULT;
  const alpacaFeed =
    typeof row.data_feed === 'string' && row.data_feed
      ? row.data_feed
      : DATA_FEED_DEFAULT;
  const scannerPersistentAuthoritative = row.scanner_persistent_authoritative === true;
  return { discoveryProvider, alpacaFeed, scannerPersistentAuthoritative };
}
