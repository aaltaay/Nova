/**
 * Quick Trades as one icon-labelled row: every shown action keeps its
 * dispatch, depth-gated actions grey out without a live book, and the gear
 * opens Settings > Hot Keys.
 *
 * @vitest-environment jsdom
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, useEffect } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { NOVA_ACTION_DEPTH_DISABLED_REASON } from '../constants';
import { createDefaultNovaActions } from './novaActionDefaults';
import type { NovaActionRecord } from './novaActionTypes';
import { TopOfBookProvider, useTopOfBook, type TopOfBook } from './TopOfBookContext';
import { TradingQuickBar } from './TradingQuickBar';

const state = vi.hoisted(() => ({
  actions: [] as NovaActionRecord[],
  runAction: vi.fn(),
  lastResult: null as { ok: boolean; text: string } | null,
  openSettings: vi.fn(),
  settings: true,
}));

vi.mock('./HotkeyDispatchContext', () => ({
  useHotkeyDispatchOptional: () => ({
    novaActions: state.actions,
    runAction: state.runAction,
    lastResult: state.lastResult,
  }),
}));

vi.mock('../settings/SettingsContext', () => ({
  useSettingsOptional: () => (state.settings ? { openSettings: state.openSettings } : null),
}));

function BookSetter({ book }: { book: TopOfBook | null }) {
  const { setTopOfBook } = useTopOfBook();
  useEffect(() => {
    setTopOfBook(book);
  }, [book, setTopOfBook]);
  return null;
}

describe('TradingQuickBar', () => {
  let mount: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    state.actions = createDefaultNovaActions();
    state.runAction.mockReset();
    state.runAction.mockResolvedValue({ ok: true, text: 'ok' });
    state.openSettings.mockReset();
    state.lastResult = null;
    state.settings = true;
    mount = document.createElement('div');
    document.body.appendChild(mount);
    root = createRoot(mount);
  });

  afterEach(() => {
    act(() => root.unmount());
    mount.remove();
  });

  function render(book: TopOfBook | null = null) {
    act(() => {
      root.render(
        <TopOfBookProvider>
          <BookSetter book={book} />
          <TradingQuickBar />
        </TopOfBookProvider>,
      );
    });
  }

  const buttons = () =>
    Array.from(mount.querySelectorAll<HTMLButtonElement>('[data-testid="quick-trades-row"] .nova-qt__btn[data-kind]'));

  it('renders one row: every shown action as icon + short label, full name as tooltip', () => {
    render();
    expect(mount.querySelector('[data-testid="quick-trades-row"]')?.getAttribute('role')).toBe('toolbar');
    const shown = state.actions.filter((a) => a.enabled && a.showButton);
    expect(buttons().length).toBe(shown.length);
    const flatten = buttons().find((b) => b.dataset.kind === 'exit_pos')!;
    expect(flatten.textContent).toBe('Flatten');
    expect(flatten.title).toContain('Flatten position');
    expect(flatten.classList.contains('nova-qt__btn--protective')).toBe(true);
    expect(flatten.querySelector('svg')).toBeTruthy();
    const buy = buttons().find((b) => b.dataset.kind === 'buy_market')!;
    expect(buy.classList.contains('nova-qt__btn--buy')).toBe(true);
    const cancel = buttons().find((b) => b.dataset.kind === 'cancel_symbol')!;
    expect(cancel.classList.contains('nova-qt__btn--cancel')).toBe(true);
    // No collapse toggle and no caption: the row is the whole affordance.
    expect(mount.querySelector('[data-testid="quick-trades-toggle"]')).toBeNull();
  });

  it('renders each label word as its own box, so a label never breaks inside a word (QA D14)', () => {
    render();
    const words = (kind: string) =>
      Array.from(buttons().find((b) => b.dataset.kind === kind)!.querySelectorAll('.nova-qt__label > .nova-qt__word'))
        .map((w) => w.textContent);
    expect(words('cancel_and_exit')).toEqual(['Cxl+', 'Flat']);
    expect(words('exit_pos')).toEqual(['Flatten']);
    expect(words('cancel_symbol')).toEqual(['Cxl', 'sym']);
    expect(buttons().find((b) => b.dataset.kind === 'cancel_symbol')!.textContent).toBe('Cxl sym');
  });

  it('keeps every dispatch: a click runs that action', () => {
    render();
    const cancelAll = buttons().find((b) => b.dataset.kind === 'cancel_all_orders')!;
    act(() => cancelAll.click());
    expect(state.runAction).toHaveBeenCalledTimes(1);
    expect(state.runAction.mock.calls[0][0].id).toBe('nova-wb-cancel-all');
  });

  it('greys depth-dependent actions with the reason until the book is live', () => {
    render();
    const askBuy = () => buttons().find((b) => b.dataset.kind === 'buy_limit_ask_offset')!;
    expect(askBuy().disabled).toBe(true);
    // The reason rides on data-why (ux/whyTip.ts); no native title stacks on it.
    expect(askBuy().dataset.why).toBe(NOVA_ACTION_DEPTH_DISABLED_REASON);
    expect(askBuy().hasAttribute('title')).toBe(false);
    render({ symbol: 'GRML', bid: 8.89, ask: 8.91, depthSubscribed: true });
    expect(askBuy().disabled).toBe(false);
    expect(askBuy().dataset.why).toBeUndefined();
    expect(askBuy().title).toContain('F1');
  });

  it('ends the row with a gear that opens Settings > Hot Keys', () => {
    render();
    const gear = mount.querySelector<HTMLButtonElement>('[data-testid="quick-trades-customize"]')!;
    expect(gear).toBeTruthy();
    act(() => gear.click());
    expect(state.openSettings).toHaveBeenCalledWith('hotkeys');
  });

  it('omits the gear when no Settings host is mounted (pop-out windows)', () => {
    state.settings = false;
    render();
    expect(mount.querySelector('[data-testid="quick-trades-customize"]')).toBeNull();
    expect(buttons().length).toBeGreaterThan(0);
  });

  it('shows the last action result under the row', () => {
    state.lastResult = { ok: false, text: 'Refused PRACTICE_NO_SHORTS' };
    render();
    const status = mount.querySelector('[role="status"]');
    expect(status?.textContent).toBe('Refused PRACTICE_NO_SHORTS');
    expect(status?.classList.contains('err')).toBe(true);
  });

  it('leaves the result to a host whose ticket shows it (QA R35)', () => {
    state.lastResult = { ok: true, text: 'Exit order #12' };
    act(() => {
      root.render(
        <TopOfBookProvider>
          <TradingQuickBar status={false} />
        </TopOfBookProvider>,
      );
    });
    expect(mount.querySelector('[role="status"]')).toBeNull();
    expect(buttons().length).toBeGreaterThan(0);
  });
});
