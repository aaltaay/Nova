import { describe, expect, it } from 'vitest';
import {
  TRADER_DESK_PROTOCOL_V,
  encodeTraderTabDrag,
  parseTraderDeskMessage,
  parseTraderTabDrag,
  traderDeskMessage,
} from './protocol';

describe('trader desk protocol', () => {
  it('round-trips a tab drag payload and rejects garbage', () => {
    const raw = encodeTraderTabDrag({
      symbol: 'ipst',
      sourceWindowId: 'win-a',
    });
    expect(parseTraderTabDrag(raw)).toEqual({
      v: TRADER_DESK_PROTOCOL_V,
      symbol: 'IPST',
      sourceWindowId: 'win-a',
    });
    expect(parseTraderTabDrag('not-json')).toBeNull();
    expect(parseTraderTabDrag(JSON.stringify({ symbol: 'X' }))).toBeNull();
    expect(parseTraderTabDrag(encodeTraderTabDrag({ symbol: '', sourceWindowId: 'w' }))).toBeNull();
  });

  it('parses desk bus messages and ignores other traffic', () => {
    const docked = traderDeskMessage('tab-docked', {
      symbol: 'SPY',
      sourceWindowId: 'float-1',
      targetWindowId: 'host-1',
    });
    expect(parseTraderDeskMessage(docked)).toEqual({
      v: TRADER_DESK_PROTOCOL_V,
      type: 'tab-docked',
      symbol: 'SPY',
      sourceWindowId: 'float-1',
      targetWindowId: 'host-1',
    });
    expect(parseTraderDeskMessage({ type: 'unrelated' })).toBeNull();
    expect(parseTraderDeskMessage(null)).toBeNull();
    const rejected = traderDeskMessage('dock-reject', {
      symbol: 'QQQ',
      sourceWindowId: 'float-1',
      requestId: 'req-9',
    });
    expect(parseTraderDeskMessage(rejected)?.type).toBe('dock-reject');
  });
});
