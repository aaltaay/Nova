import { describe, expect, it } from 'vitest';
import {
  alignIbcConfigIni,
  ibcConfigHasCredentials,
} from './alignIbcConfig';

const SAMPLE = [
  'IbLoginId=paperuser',
  'IbLoginIdLive=liveuser',
  'IbLoginIdPaper=paperuser',
  'IbPassword=secret',
  'TradingMode=paper',
  'OverrideTwsApiPort=4002',
].join('\n');

describe('alignIbcConfigIni', () => {
  it('copies the live login id and live port onto the active keys', () => {
    const out = alignIbcConfigIni(SAMPLE, 'live');
    expect(out).toMatch(/^IbLoginId=liveuser$/m);
    expect(out).toMatch(/^TradingMode=live$/m);
    expect(out).toMatch(/^OverrideTwsApiPort=4001$/m);
    expect(ibcConfigHasCredentials(out)).toBe(true);
  });

  it('copies the paper login id back', () => {
    const out = alignIbcConfigIni(SAMPLE, 'paper');
    expect(out).toMatch(/^IbLoginId=paperuser$/m);
    expect(out).toMatch(/^OverrideTwsApiPort=4002$/m);
  });

  it('reports missing password so Open live cannot fake a fill', () => {
    expect(ibcConfigHasCredentials('IbLoginId=alice\nTradingMode=live\n')).toBe(false);
  });
});
