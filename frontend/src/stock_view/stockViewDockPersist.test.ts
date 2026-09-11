/**
 * @vitest-environment jsdom
 */
import { beforeEach, describe, expect, it } from 'vitest';
import { STOCK_VIEW_OPEN_ORDERS_SAMPLE_HIDDEN_KEY } from '../constants';
import { initialSampleHidden } from './stockViewDockPersist';

describe('initialSampleHidden', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('hides sample when global Sample mode is off', () => {
    expect(initialSampleHidden(false)).toBe(true);
  });

  it('shows sample when global Sample mode is on and nothing was hidden', () => {
    expect(initialSampleHidden(true)).toBe(false);
  });

  it('keeps a stored Hide even under Sample mode', () => {
    localStorage.setItem(STOCK_VIEW_OPEN_ORDERS_SAMPLE_HIDDEN_KEY, '1');
    expect(initialSampleHidden(true)).toBe(true);
  });
});
