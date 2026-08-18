import { describe, expect, it } from 'vitest';
import { shouldPaintOscillator } from './oscillatorPaint';

describe('shouldPaintOscillator', () => {
  it('does not skip when series are missing -- key must stay unconsumed', () => {
    expect(shouldPaintOscillator(false, '', '0:macd:50')).toBe(false);
    expect(shouldPaintOscillator(false, '0:macd:50', '0:macd:50')).toBe(false);
  });

  it('paints once the pane series exist and the key is new', () => {
    expect(shouldPaintOscillator(true, '', '1:macd:50')).toBe(true);
    expect(shouldPaintOscillator(true, '1:macd:50', '1:macd:50')).toBe(false);
    expect(shouldPaintOscillator(true, '1:macd:50', '2:macd:50')).toBe(true);
  });
});
