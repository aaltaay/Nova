import { describe, expect, it } from 'vitest';
import {
  buildMappedNovaAction,
  resetMapIdSeqForTests,
  suggestNovaActionFromDas,
} from './mapDasToNovaAction';

describe('suggestNovaActionFromDas', () => {
  it('maps CXL ALLSYMB to cancel_symbol', () => {
    const s = suggestNovaActionFromDas('CXL ALLSYMB');
    expect(s.ok).toBe(true);
    if (s.ok) expect(s.kind).toBe('cancel_symbol');
  });

  it('maps Share=Pos sell to exit_pos', () => {
    const s = suggestNovaActionFromDas(
      'ROUTE=MARKET;Share=Pos;TIF=DAY+;SELL=Send',
    );
    expect(s.ok).toBe(true);
    if (s.ok) expect(s.kind).toBe('exit_pos');
  });

  it('maps Share=Pos*0.5 to exit_pos_pct', () => {
    const s = suggestNovaActionFromDas(
      'ROUTE=MARKET;Share=Pos*0.5;TIF=DAY+;SELL=Send',
    );
    expect(s.ok).toBe(true);
    if (s.ok) {
      expect(s.kind).toBe('exit_pos_pct');
      expect(s.params.percent).toBe(50);
    }
  });

  it('maps Ask+ offset buy to buy_limit_ask_offset', () => {
    const s = suggestNovaActionFromDas(
      'ROUTE=LIMIT;Price=Ask+0.05;Share=100;TIF=DAY+;BUY=Send',
    );
    expect(s.ok).toBe(true);
    if (s.ok) {
      expect(s.kind).toBe('buy_limit_ask_offset');
      expect(s.params.shares).toBe(100);
      expect(s.params.offsetDollars).toBe(0.05);
    }
  });

  it('rejects TriggerOrder scripts', () => {
    const s = suggestNovaActionFromDas(
      'ROUTE=LIMIT;Price=Ask+0.10;Share=100;BUY=Send;TriggerOrder=RT:STOP STOPTYPE:MARKET',
    );
    expect(s.ok).toBe(false);
  });
});

describe('buildMappedNovaAction', () => {
  it('creates a disabled Nova Action preserving the key', () => {
    resetMapIdSeqForTests();
    const suggestion = suggestNovaActionFromDas('CXL ALLSYMB');
    expect(suggestion.ok).toBe(true);
    if (!suggestion.ok) return;
    const mapped = buildMappedNovaAction(
      {
        id: 'r1',
        name: 'Cancel symb',
        key: { label: 'Shift+Backspace', key: 'Backspace', shift: true },
        command: 'CXL ALLSYMB',
      },
      suggestion,
    );
    expect(mapped.enabled).toBe(false);
    expect(mapped.showButton).toBe(false);
    expect(mapped.key.key).toBe('Backspace');
    expect(mapped.kind).toBe('cancel_symbol');
  });
});
