/**
 * @vitest-environment jsdom
 */
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { HodMomoSoundToggle } from './HodMomoSoundToggle';
import {
  HOD_MOMO_ALERT_SOUND_STORAGE_KEY,
  isHodMomoAlertSoundOn,
  resetHodMomoAlertPingForTests,
} from './hodMomoAlertPing';

describe('HodMomoSoundToggle', () => {
  beforeEach(() => {
    resetHodMomoAlertPingForTests();
  });

  afterEach(() => {
    cleanup();
    resetHodMomoAlertPingForTests();
  });

  it('defaults on and writes localStorage when toggled off', () => {
    render(<HodMomoSoundToggle />);
    const btn = screen.getByTestId('hod-momo-sound-toggle');
    expect(btn.getAttribute('aria-pressed')).toBe('true');
    fireEvent.click(btn);
    expect(btn.getAttribute('aria-pressed')).toBe('false');
    expect(isHodMomoAlertSoundOn()).toBe(false);
    expect(localStorage.getItem(HOD_MOMO_ALERT_SOUND_STORAGE_KEY)).toBe('0');
  });
});
