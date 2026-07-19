import { describe, expect, it } from 'vitest';
import {
  chordToTanstackHotkey,
  chordsEqualTanstack,
  tanstackHotkeyToChord,
} from './tanstackChord';

describe('tanstackChord', () => {
  it('round-trips Control+Shift+A via TanStack normalize', () => {
    const chord = tanstackHotkeyToChord('Control+Shift+A');
    expect(chord.ctrl).toBe(true);
    expect(chord.shift).toBe(true);
    expect(chord.key.toLowerCase()).toBe('a');
    expect(chordToTanstackHotkey(chord)).toBe(
      chordToTanstackHotkey({
        label: 'Ctrl+Shift+A',
        key: 'a',
        ctrl: true,
        shift: true,
      }),
    );
  });

  it('detects equal chords with TanStack normalize', () => {
    expect(
      chordsEqualTanstack(
        { label: 'Ctrl+M', key: 'm', ctrl: true },
        { label: 'Control+M', key: 'M', ctrl: true },
      ),
    ).toBe(true);
  });
});
