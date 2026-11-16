/**
 * @vitest-environment jsdom
 */
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { deskSoundOn, resetDeskSoundsForTests, setDeskMuted, setDeskSoundLevel, setDeskSoundOn } from '../sound';
import { resetStreamSoundForTests, wireStreamWindow } from '../sound/streamSound';
import { StreamPlayer } from './StreamPlayer';

function commands(frame: HTMLIFrameElement) {
  const post = vi.fn();
  Object.defineProperty(frame, 'contentWindow', { value: { postMessage: post } });
  return () => post.mock.calls.map(([msg]) => {
    const { func, args } = JSON.parse(msg as string) as { func: string; args: number[] };
    return args.length ? `${func} ${args.join(' ')}` : func;
  });
}

describe('StreamPlayer under the header mute', () => {
  beforeEach(() => {
    localStorage.clear();
    setDeskMuted(false);
    resetDeskSoundsForTests();
    resetStreamSoundForTests();
  });
  afterEach(() => {
    cleanup();
    setDeskMuted(false);
  });

  it('the header mute mutes the stream and holds its sound button, saying why', () => {
    render(<StreamPlayer videoId="abcdefghijk" title="Live" offAir={null} />);
    const btn = screen.getByTestId('ft-stream-sound');
    fireEvent.click(btn);
    expect(btn.getAttribute('aria-pressed')).toBe('true'); // sound on
    act(() => setDeskMuted(true));
    expect(btn.getAttribute('aria-pressed')).toBe('false');
    expect((btn as HTMLButtonElement).disabled).toBe(true);
    expect(btn.getAttribute('data-why')).toMatch(/header mute is on/);
    fireEvent.click(btn);
    expect(btn.getAttribute('aria-pressed')).toBe('false'); // held: still muted
    act(() => setDeskMuted(false));
    expect((btn as HTMLButtonElement).disabled).toBe(false);
    expect(btn.getAttribute('aria-pressed')).toBe('false'); // back on, the stream stays muted until asked
  });
});

describe('StreamPlayer and the YouTube row', () => {
  beforeEach(() => {
    localStorage.clear();
    setDeskMuted(false);
    resetDeskSoundsForTests();
    resetStreamSoundForTests();
  });
  afterEach(() => {
    cleanup();
    delete (window as { novaDesktop?: unknown }).novaDesktop;
  });

  it('starts muted, and the row turns it on at its volume', () => {
    render(<StreamPlayer videoId="abcdefghijk" title="Live" offAir={null} />);
    const seen = commands(screen.getByTestId('ft-stream-frame') as HTMLIFrameElement);
    const btn = screen.getByTestId('ft-stream-sound');
    expect(btn.getAttribute('aria-pressed')).toBe('false');
    act(() => setDeskSoundOn('stream', true));
    expect(btn.getAttribute('aria-pressed')).toBe('true');
    expect(seen()).toEqual(['setVolume 50', 'unMute']);
    act(() => setDeskSoundLevel('stream', 30));
    expect(seen()).toContain('setVolume 30');
    act(() => setDeskSoundOn('stream', false));
    expect(seen().at(-1)).toBe('mute');
  });

  it('its own button is the same switch as the row', () => {
    render(<StreamPlayer videoId="abcdefghijk" title="Live" offAir={null} />);
    fireEvent.click(screen.getByTestId('ft-stream-sound'));
    expect(deskSoundOn('stream')).toBe(true);
  });

  it('a reload, a closed player or going off air leaves the next one muted', () => {
    const { rerender, unmount } = render(<StreamPlayer videoId="abcdefghijk" title="Live" offAir={null} />);
    act(() => setDeskSoundOn('stream', true));
    fireEvent.click(screen.getByTestId('ft-stream-reload'));
    expect(deskSoundOn('stream')).toBe(false);
    act(() => setDeskSoundOn('stream', true));
    rerender(<StreamPlayer videoId="abcdefghijk" title="Live" offAir="last read 15:57:12 ET" />);
    expect(deskSoundOn('stream')).toBe(false);
    rerender(<StreamPlayer videoId="abcdefghijk" title="Live" offAir={null} />);
    act(() => setDeskSoundOn('stream', true));
    unmount();
    expect(deskSoundOn('stream')).toBe(false);
  });

  it('gives the sound to the pop-out while it is open, and holds its button, saying why', () => {
    let tellOpen: (open: boolean) => void = () => undefined;
    (window as { novaDesktop?: unknown }).novaDesktop = {
      isDesktop: true,
      apiBase: '',
      setStreamSound: vi.fn(),
      onStreamWindow: (cb: (open: boolean) => void) => {
        tellOpen = cb;
        return () => undefined;
      },
    };
    const unwire = wireStreamWindow();
    render(<StreamPlayer videoId="abcdefghijk" title="Live" offAir={null} />);
    const btn = screen.getByTestId('ft-stream-sound') as HTMLButtonElement;
    const seen = commands(screen.getByTestId('ft-stream-frame') as HTMLIFrameElement);
    act(() => tellOpen(true));
    expect(deskSoundOn('stream')).toBe(true);
    expect(btn.getAttribute('aria-pressed')).toBe('false');
    expect(btn.disabled).toBe(true);
    expect(btn.getAttribute('data-why')).toMatch(/pop-out has the sound/);
    expect(seen()).not.toContain('unMute');
    act(() => tellOpen(false));
    expect(deskSoundOn('stream')).toBe(false);
    expect(btn.disabled).toBe(false);
    expect(seen()).not.toContain('unMute');
    unwire();
  });
});
