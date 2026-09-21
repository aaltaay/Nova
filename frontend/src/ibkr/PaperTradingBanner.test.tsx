/** @vitest-environment jsdom */
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { PaperTradingBanner } from './PaperTradingBanner';

afterEach(cleanup);

describe('PaperTradingBanner (ADR 020)', () => {
  it("says orders go to Nova's practice account -- fake money on the live feed, never IBKR", () => {
    render(<PaperTradingBanner mode="paper" />);
    const banner = screen.getByTestId('paper-trading-banner');
    expect(banner.textContent).toMatch(/Nova's practice account/);
    expect(banner.textContent).toMatch(/fake money/i);
    expect(banner.textContent).toMatch(/live feed/i);
    expect(banner.textContent).not.toMatch(/IBKR paper account/);
  });

  it('shows nothing on Live, Sim or while disconnected', () => {
    for (const mode of ['live', 'sim', 'disconnected'] as const) {
      render(<PaperTradingBanner mode={mode} />);
      expect(screen.queryByTestId('paper-trading-banner')).toBeNull();
      cleanup();
    }
  });
});
