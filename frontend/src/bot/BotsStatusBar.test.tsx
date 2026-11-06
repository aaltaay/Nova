/** @vitest-environment jsdom */
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { BotsStatusBar } from './BotsStatusBar';
import type { BotSession } from './types';

const desk = vi.hoisted(() => ({
  split: true,
  botsBook: new Map<string, number>(),
  positions: [] as { symbol: string; qty: number }[],
  orders: [] as { owner?: string | null }[],
  symbol: 'ORCL' as string | null,
}));

vi.mock('../ibkr', () => ({ useDeskPositions: () => ({ split: desk.split, botsBook: desk.botsBook }) }));
vi.mock('../ibkr/IbkrAccountContext', () => ({
  useOptionalIbkrAccountContext: () => ({ positions: desk.positions, orders: desk.orders }),
}));
vi.mock('../workspace', () => ({ useWorkspace: () => ({ selectedSymbol: desk.symbol }) }));

const session = (working: number) => ({
  working: Array.from({ length: working }, () => ({})),
  caps: { api_kinds: ['market'] },
}) as unknown as BotSession;

const line = () => screen.getByTestId('bots-status').querySelector('span')?.textContent;

beforeEach(() => {
  desk.split = true;
  desk.botsBook = new Map();
  desk.positions = [];
  desk.orders = [];
  desk.symbol = 'ORCL';
});
afterEach(cleanup);

describe('BotsStatusBar (ADR 069 decision 9)', () => {
  it("reads the bots' own book on Paper: their shares, and every bot's working orders", () => {
    desk.botsBook = new Map([['ORCL', -19]]);
    desk.orders = [{ owner: 'bots' }, { owner: 'you' }];
    render(<BotsStatusBar session={session(0)} />);
    expect(line()).toBe('ORCL · bots -19 sh · 1 bot working order');
  });

  it('says flat while the bots hold none of it, whatever you hold', () => {
    desk.positions = [{ symbol: 'ORCL', qty: 100 }];
    render(<BotsStatusBar session={session(0)} />);
    expect(line()).toBe('ORCL · flat · 0 bot working orders');
  });

  it('keeps the account and the session on Sim, where there is one book', () => {
    desk.split = false;
    desk.positions = [{ symbol: 'ORCL', qty: 40 }];
    render(<BotsStatusBar session={session(2)} />);
    expect(line()).toBe('ORCL · +40 sh · 2 bot working orders');
  });
});
