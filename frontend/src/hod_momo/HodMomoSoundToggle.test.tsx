/**
 * @vitest-environment jsdom
 */
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { HodMomoSoundToggle } from './HodMomoSoundToggle';
import {
  HOD_MOMO_ALERT_SOUND_KEY,
  isHodMomoAlertSoundOn,
  resetHodMomoAlertSoundForTests,
} from './hodMomoAlertSound';

describe('HodMomoSoundToggle', () => {
  beforeEach(() => {
    resetHodMomoAlertSoundForTests();
  });

  afterEach(() => {
    cleanup();
    resetHodMomoAlertSoundForTests();
  });

  it('defaults on and persists off after click', () => {
    render(<HodMomoSoundToggle className="hod-sound-btn" />);
    const btn = screen.getByTestId('hod-momo-sound-toggle');
    expect(btn.getAttribute('aria-pressed')).toBe('true');
    expect(isHodMomoAlertSoundOn()).toBe(true);
    fireEvent.click(btn);
    expect(btn.getAttribute('aria-pressed')).toBe('false');
    expect(isHodMomoAlertSoundOn()).toBe(false);
    expect(localStorage.getItem(HOD_MOMO_ALERT_SOUND_KEY)).toBe('0');
  });
});
