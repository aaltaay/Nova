import { describe, expect, it } from 'vitest';
import {
  inferOrderRejectReason,
  orderRejectTitle,
  orderRejectTone,
} from './notifyOrderRejected';

describe('notifyOrderRejected copy', () => {
  it('titles BUYING_POWER as not enough buying power', () => {
    expect(orderRejectTitle('BUYING_POWER')).toBe('Not enough buying power');
    expect(orderRejectTone('BUYING_POWER')).toBe('warning');
  });

  it('infers BUYING_POWER from the validate error string', () => {
    expect(
      inferOrderRejectReason(
        'estimated notional 596.54 exceeds BuyingPower 552.79',
      ),
    ).toBe('BUYING_POWER');
  });

  it('keeps a generic title for unknown codes', () => {
    expect(orderRejectTitle('MADE_UP')).toBe('Order rejected');
    expect(orderRejectTone('BROKER_REJECT')).toBe('danger');
  });
});
