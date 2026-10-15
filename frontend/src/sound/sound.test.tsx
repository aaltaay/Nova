/**
 * @vitest-environment jsdom
 */
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { DESK_SOUND_MUTED_KEY, DESK_VOICE_MAX_QUEUED } from './constants';
import { DeskMuteButton } from './DeskMuteButton';
import { isDeskMuted, resetDeskMuteForTests, setDeskMuted, subscribeDeskMute } from './deskMute';
import { deskVoiceProblem, resetDeskVoiceForTests, speakDesk } from './speech';

class FakeUtterance {
  text: string;
  voice: unknown = null;
  lang = '';
  rate = 1;
  onend: (() => void) | null = null;
  onerror: ((ev: { error: string }) => void) | null = null;
  constructor(text: string) {
    this.text = text;
  }
}

function fakeSpeech() {
  const said: FakeUtterance[] = [];
  const synth = {
    paused: false,
    speak: vi.fn((u: FakeUtterance) => said.push(u)),
    cancel: vi.fn(),
    resume: vi.fn(),
    getVoices: () => [
      { lang: 'fr-FR', localService: true, name: 'Hortense' },
      { lang: 'en-US', localService: true, name: 'David' },
    ],
  };
  vi.stubGlobal('SpeechSynthesisUtterance', FakeUtterance);
  vi.stubGlobal('speechSynthesis', synth);
  return { synth, said };
}

beforeEach(() => {
  localStorage.clear();
  resetDeskMuteForTests();
  resetDeskVoiceForTests();
});

afterEach(() => {
  cleanup();
  setDeskMuted(false);
  vi.unstubAllGlobals();
  delete (window as { novaDesktop?: unknown }).novaDesktop;
});

describe('the header mute', () => {
  it('is sound on until the operator mutes, and remembers the switch', () => {
    expect(isDeskMuted()).toBe(false);
    setDeskMuted(true);
    expect(JSON.parse(localStorage.getItem(DESK_SOUND_MUTED_KEY) ?? 'null')).toEqual({ schema_version: 1, value: true });
    resetDeskMuteForTests();
    expect(isDeskMuted()).toBe(true);
  });

  it('reads an unknown version as sound on', () => {
    localStorage.setItem(DESK_SOUND_MUTED_KEY, JSON.stringify({ schema_version: 99, value: true }));
    resetDeskMuteForTests();
    expect(isDeskMuted()).toBe(false);
  });

  it('follows a click in another window, and tells the desktop app', () => {
    const setSoundMuted = vi.fn();
    (window as { novaDesktop?: unknown }).novaDesktop = { isDesktop: true, apiBase: '', setSoundMuted };
    const seen: boolean[] = [];
    const off = subscribeDeskMute(m => seen.push(m));
    localStorage.setItem(DESK_SOUND_MUTED_KEY, JSON.stringify({ schema_version: 1, value: true }));
    window.dispatchEvent(new StorageEvent('storage', { key: DESK_SOUND_MUTED_KEY }));
    expect(isDeskMuted()).toBe(true);
    expect(seen).toEqual([true]);
    expect(setSoundMuted).toHaveBeenLastCalledWith(true);
    off();
  });
});

describe('the desk voice', () => {
  it('speaks in an English voice on this PC', () => {
    const { said } = fakeSpeech();
    expect(speakDesk('Bought 100 shares of S O F I.')).toBe('spoken');
    expect(said[0].text).toBe('Bought 100 shares of S O F I.');
    expect((said[0].voice as { name: string }).name).toBe('David');
  });

  it('says nothing while muted, and a mute cuts a sentence off', () => {
    const { synth } = fakeSpeech();
    speakDesk('Sold 100 shares of S O F I.');
    setDeskMuted(true);
    expect(synth.cancel).toHaveBeenCalled();
    expect(speakDesk('Sold 100 shares of S O F I.')).toBe('muted');
    expect(synth.speak).toHaveBeenCalledTimes(1);
  });

  it('drops what waits once the queue is long, for the newest', () => {
    const { synth } = fakeSpeech();
    for (let i = 0; i < DESK_VOICE_MAX_QUEUED; i += 1) speakDesk(`fill ${i}`);
    expect(synth.cancel).not.toHaveBeenCalled();
    speakDesk('newest');
    expect(synth.cancel).toHaveBeenCalledTimes(1);
  });

  it('keeps why it could not speak, and clears it when a sentence ends', () => {
    const { said } = fakeSpeech();
    speakDesk('Order rejected.');
    act(() => said[0].onerror?.({ error: 'not-allowed' }));
    expect(deskVoiceProblem()).toMatch(/click in this window/);
    speakDesk('Sound on.');
    act(() => said[1].onend?.());
    expect(deskVoiceProblem()).toBeNull();
  });

  it('a cancel on purpose is no problem', () => {
    const { said } = fakeSpeech();
    speakDesk('Bought 1 share of A.');
    said[0].onerror?.({ error: 'interrupted' });
    expect(deskVoiceProblem()).toBeNull();
  });

  it('says so when the browser has no speech', () => {
    vi.stubGlobal('speechSynthesis', undefined);
    expect(speakDesk('Bought 1 share of A.')).toBe('unavailable');
    expect(deskVoiceProblem()).toMatch(/no speech/);
  });
});

describe('DeskMuteButton', () => {
  it('mutes with one click and turns sound back on with another, saying so', () => {
    const { said } = fakeSpeech();
    render(<DeskMuteButton />);
    const btn = screen.getByTestId('global-bar-mute');
    expect(btn.getAttribute('aria-pressed')).toBe('false');
    expect(btn.getAttribute('aria-label')).toBe('Sound on');
    fireEvent.click(btn);
    expect(isDeskMuted()).toBe(true);
    expect(btn.getAttribute('aria-pressed')).toBe('true');
    expect(btn.getAttribute('aria-label')).toBe('Sound muted');
    expect(btn.title).toMatch(/every Nova sound is off/);
    expect(said).toHaveLength(0);
    fireEvent.click(btn);
    expect(isDeskMuted()).toBe(false);
    expect(said.map(u => u.text)).toEqual(['Sound on.']);
  });

  it('shows why the voice cannot speak on hover', () => {
    vi.stubGlobal('speechSynthesis', undefined);
    render(<DeskMuteButton />);
    act(() => {
      speakDesk('Bought 1 share of A.');
    });
    expect(screen.getByTestId('global-bar-mute').title).toMatch(/cannot speak in this window: this browser has no speech/);
  });
});
