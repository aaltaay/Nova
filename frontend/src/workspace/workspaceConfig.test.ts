import { describe, expect, it } from 'vitest';
import {
  DATA_FEED_DEFAULT,
  DISCOVERY_PROVIDER_DEFAULT,
} from '../constants';
import {
  WORKSPACE_CONFIG_DEFAULTS,
  parseWorkspaceConfig,
} from './workspaceConfig';

describe('parseWorkspaceConfig', () => {
  it('returns defaults for null/invalid payloads', () => {
    expect(parseWorkspaceConfig(null)).toEqual(WORKSPACE_CONFIG_DEFAULTS);
    expect(parseWorkspaceConfig(undefined)).toEqual(WORKSPACE_CONFIG_DEFAULTS);
    expect(parseWorkspaceConfig('oops')).toEqual(WORKSPACE_CONFIG_DEFAULTS);
    expect(WORKSPACE_CONFIG_DEFAULTS).toEqual({
      discoveryProvider: DISCOVERY_PROVIDER_DEFAULT,
      alpacaFeed: DATA_FEED_DEFAULT,
    });
  });

  it('loads discovery_provider and data_feed from /api/config shape', () => {
    expect(
      parseWorkspaceConfig({
        discovery_provider: 'ibkr',
        data_feed: 'sip',
      }),
    ).toEqual({ discoveryProvider: 'ibkr', alpacaFeed: 'sip' });
  });

  it('falls back per-field when values are missing', () => {
    expect(parseWorkspaceConfig({ discovery_provider: 'ibkr' })).toEqual({
      discoveryProvider: 'ibkr',
      alpacaFeed: DATA_FEED_DEFAULT,
    });
    expect(parseWorkspaceConfig({ data_feed: 'sip' })).toEqual({
      discoveryProvider: DISCOVERY_PROVIDER_DEFAULT,
      alpacaFeed: 'sip',
    });
  });
});
