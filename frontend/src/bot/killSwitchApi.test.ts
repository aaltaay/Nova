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
});
