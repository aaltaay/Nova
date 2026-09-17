import { describe, expect, it, beforeEach } from 'vitest';
import {
  beginDeskAction,
  deskActionInFlight,
  resetDeskActionForTests,
  subscribeDeskAction,
} from './deskActionFlight';

describe('deskActionFlight', () => {
  beforeEach(() => {
    resetDeskActionForTests();
  });

  it('tracks overlapping Place / Flatten / Fill now', () => {
    expect(deskActionInFlight()).toBe(false);
    const endPlace = beginDeskAction();
    const endFill = beginDeskAction();
    expect(deskActionInFlight()).toBe(true);
    endPlace();
    expect(deskActionInFlight()).toBe(true);
    endFill();
    expect(deskActionInFlight()).toBe(false);
  });

  it('notifies subscribers', () => {
    let seen = 0;
    const stop = subscribeDeskAction(() => {
      seen += 1;
    });
    const end = beginDeskAction();
    end();
    stop();
    expect(seen).toBe(2);
  });
});
