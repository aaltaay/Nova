import { describe, expect, it } from 'vitest';
import {
  initialBareModifierRecordState,
  reduceBareModifierRecordKeyDown,
  reduceBareModifierRecordKeyUp,
} from './bareModifierRecord';

describe('bareModifierRecord', () => {
  it('records bare Alt on keyup when no other key was pressed', () => {
    let state = initialBareModifierRecordState();
    state = reduceBareModifierRecordKeyDown(state, { key: 'Alt', code: 'AltLeft' });
    const up = reduceBareModifierRecordKeyUp(state, { key: 'Alt', code: 'AltLeft' });
    expect(up.chord).toEqual({ key: 'Alt', label: 'Alt' });
  });

  it('records Ctrl+Alt after both modifiers are released', () => {
    let state = initialBareModifierRecordState();
    state = reduceBareModifierRecordKeyDown(state, {
      key: 'Control',
      code: 'ControlLeft',
    });
    state = reduceBareModifierRecordKeyDown(state, { key: 'Alt', code: 'AltLeft' });
    state = reduceBareModifierRecordKeyUp(state, { key: 'Alt', code: 'AltLeft' }).state;
    const up = reduceBareModifierRecordKeyUp(state, {
      key: 'Control',
      code: 'ControlLeft',
    });
    expect(up.chord).toEqual({
      key: 'Alt',
      label: 'Ctrl+Alt',
      ctrl: true,
    });
  });

  it('does not record when a letter is pressed while Alt is held', () => {
    let state = initialBareModifierRecordState();
    state = reduceBareModifierRecordKeyDown(state, { key: 'Alt', code: 'AltLeft' });
    state = reduceBareModifierRecordKeyDown(state, { key: 'a', code: 'KeyA' });
    const up = reduceBareModifierRecordKeyUp(state, { key: 'Alt', code: 'AltLeft' });
    expect(up.chord).toBeNull();
  });

  it('matches Alt via code when key name is odd', () => {
    let state = initialBareModifierRecordState();
    state = reduceBareModifierRecordKeyDown(state, { key: 'Alt', code: 'AltRight' });
    const up = reduceBareModifierRecordKeyUp(state, { key: 'Alt', code: 'AltRight' });
    expect(up.chord?.key).toBe('Alt');
  });
});
