import { describe, expect, it } from 'vitest';
import { parseKillSwitch } from './killSwitchApi';

describe('parseKillSwitch', () => {
  it('needs a boolean tripped', () => {
    expect(parseKillSwitch({ tripped: true, reason: 'kill_switch', ts: 1 })).toEqual({
      tripped: true, reason: 'kill_switch', ts: 1,
    });
    expect(parseKillSwitch({})).toBeNull();
    expect(parseKillSwitch(null)).toBeNull();
  });

  it('reads the sweep of a trip per venue, and a failed read as a failure (ADR 042 D)', () => {
    const parsed = parseKillSwitch({
      tripped: true, reason: 'kill_switch', ts: 1,
      sweep: [
        { venue: 'paper', cancelled: [101, 102], failed: [], error: null },
        { venue: 'live', cancelled: [], failed: [], error: 'Gateway disconnected: Live orders were not swept' },
      ],
      cancelled_order_ids: [101, 102], failed_cancel_order_ids: [],
    });
    expect(parsed?.sweep).toEqual([
      { venue: 'paper', cancelled: [101, 102], failed: [], error: null },
      { venue: 'live', cancelled: [], failed: [], error: 'Gateway disconnected: Live orders were not swept' },
    ]);
    // An API before ADR 042: one flat list for the account it swept.
    expect(parseKillSwitch({ tripped: true, reason: null, ts: 1, cancelled_order_ids: [7], failed_cancel_order_ids: [8] })?.sweep)
      .toEqual([{ venue: 'account', cancelled: [7], failed: [8], error: null }]);
  });
});
