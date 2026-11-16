/**
 * @vitest-environment jsdom
 */
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { templatesPayload } from './botsPageFixtures';

const calls = vi.hoisted(() => ({ board: [] as string[], tab: [] as string[] }));
vi.mock('./useSetupTemplates', () => {
  const payload = templatesPayload();
  return {
    useSetupTemplates: () => ({
      payload, error: null, refresh: vi.fn(), apply: vi.fn(),
      setup: (id: string) => payload.setups.find(s => s.id === id) ?? null,
    }),
  };
});
vi.mock('../setups', () => ({
  setupLabel: (id: string) => ({ first_pullback: 'First pullback', bull_flag: 'Bull flag' } as Record<string, string>)[id] ?? id,
  requestSetupsBoard: (id: string) => calls.board.push(id),
  useSetupsBoard: () => ({
    connected: true,
    board: { rows: [{ setup_type: 'first_pullback' }, { setup_type: 'first_pullback' }, { setup_type: 'bull_flag' }] },
  }),
}));
vi.mock('../workspace', () => ({ requestScannerTab: (tab: string) => calls.tab.push(tab) }));
vi.mock('./BotTemplateEditor', () => ({
  BotTemplateEditor: ({ open, setup }: { open: boolean; setup: { id: string } | null }) =>
    open ? <div data-testid="editor-stub">{setup?.id}</div> : null,
}));

import { StrategiesSettings } from './StrategiesSettings';

describe('Settings > Strategies (ADR 072)', () => {
  afterEach(() => {
    cleanup();
    calls.board.length = 0;
    calls.tab.length = 0;
  });

  it('lists each strategy that has a scanner, watching on Level 1, and says none places an order', () => {
    render(<StrategiesSettings />);
    const section = screen.getByTestId('settings-strategies');
    expect(section.textContent).toMatch(/None places an order, on any venue/);
    const row = screen.getByTestId('settings-strategy-first_pullback');
    expect(row.textContent).toContain('First pullback');
    expect(row.textContent).toContain('▲ LONG');
    expect(row.textContent).toContain('Level 1');
    expect(screen.getByTestId('settings-strategy-count-first_pullback').textContent).toBe('2');
  });

  it('opens the Setups board on that strategy from its count, and closes Settings', () => {
    const onClose = vi.fn();
    render(<StrategiesSettings onClose={onClose} />);
    fireEvent.click(screen.getByTestId('settings-strategy-count-first_pullback'));
    expect(calls.board).toEqual(['first_pullback']);
    expect(calls.tab).toEqual(['watchlist']);
    expect(onClose).toHaveBeenCalledOnce();
  });

  it('opens the template editor from Edit', () => {
    render(<StrategiesSettings />);
    fireEvent.click(screen.getByTestId('settings-strategy-edit-first_pullback'));
    expect(screen.getByTestId('editor-stub').textContent).toBe('first_pullback');
  });
});
