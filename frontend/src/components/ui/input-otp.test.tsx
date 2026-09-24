/** @vitest-environment jsdom */
import { render } from '@testing-library/react';
import { OTPInputContext } from 'input-otp';
import type { ComponentProps } from 'react';
import { describe, expect, it } from 'vitest';
import { InputOTPSlot } from './input-otp';

type Context = ComponentProps<typeof OTPInputContext.Provider>['value'];

const context = {
  slots: [
    { char: '7', placeholderChar: null, isActive: false, hasFakeCaret: false },
    { char: null, placeholderChar: null, isActive: true, hasFakeCaret: true },
  ],
  isFocused: true,
  isHovering: false,
} as Context;

function slot(index: number, masked: boolean) {
  const { container } = render(
    <OTPInputContext.Provider value={context}>
      <InputOTPSlot index={index} masked={masked} />
    </OTPInputContext.Provider>,
  );
  return container.querySelector('[data-slot="input-otp-slot"]')!;
}

describe('InputOTPSlot', () => {
  it('shows the typed character by default', () => {
    expect(slot(0, false).textContent).toBe('7');
  });

  it('shows a dot, never the digit, when masked', () => {
    const el = slot(0, true);
    expect(el.textContent).toBe('•');
    expect(el.textContent).not.toContain('7');
  });

  it('shows nothing for an empty masked slot', () => {
    expect(slot(1, true).textContent).toBe('');
  });
});
