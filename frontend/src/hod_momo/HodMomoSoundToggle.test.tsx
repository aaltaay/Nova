/**
 * @vitest-environment jsdom
 */
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { HOD_MOMO_ALERT_SOUND_KEY } from './hodMomoAlertSoundConstants';
import {
  isHodMomoAlertSoundEnabled,
  resetHodMomoAlertSoundForTests,
} from './hodMomoAlertSound';
import { HodMomoSoundToggle } from './HodMomoSoundToggle';

describe('HodMomoSoundToggle', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.stubGlobal('AudioContext', class {
      state = 'running';
      resume() {}
    });
    resetHodMomoAlertSoundForTests();
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    localStorage.clear();
    resetHodMomoAlertSoundForTests();
  });

  it('defaults on and persists off across remount', () => {
    const { unmount } = render(<HodMomoSoundToggle />);
    const btn = screen.getByTestId('hod-momo-sound-toggle');
    expect(btn.getAttribute('aria-pressed')).toBe('true');
    fireEvent.click(btn);
    expect(isHodMomoAlertSoundEnabled()).toBe(false);
    const stored = JSON.parse(localStorage.getItem(HOD_MOMO_ALERT_SOUND_KEY) ?? '');
    expect(stored.value).toBe(false);
    unmount();
    resetHodMomoAlertSoundForTests();
    render(<HodMomoSoundToggle />);
    expect(screen.getByTestId('hod-momo-sound-toggle').getAttribute('aria-pressed')).toBe(
      'false',
    );
  });
});
