/** @vitest-environment jsdom */
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { SCANNER_COL_ROLE, SCANNER_TABLE_WRAPPER_CLASS } from '../components/scannerTableCol';
import { DESK_BOARD_COLUMNS, DESK_BOARD_FLEX_COLUMN } from '../constantGroups/desk';
import { makeLiveScannerFeedStub } from '../scanner/ScannerDataContext';
import type { Catalyst } from '../types/catalyst';
import type { ScannerRow } from '../types/scanner';
import { DeskBoard, type DeskBoardProps } from './DeskBoard';

const here = dirname(fileURLToPath(import.meta.url));

/** Fixtures author the gap in percent; the wire carries a fraction (QA V2 / C17). */
const frac = (pct: number | null): number | null => (pct == null ? null : pct / 100);

function row(symbol: string, gap: number | null, price: number | null = 1, extra: Partial<ScannerRow> = {}): ScannerRow {
  return {
    symbol, price, prev_close: 1, change_pct: frac(gap), change_abs: null, gap_percent: frac(gap), volume: 0, rel_volume: null,
    has_news: false, newest_headline_at: null, market_cap: null, float: null, short_interest: null, short_ratio: null,
    ...extra,
  };
}

function catalyst(symbol: string, headline: string, at: string): Catalyst {
  return {
    symbol, previous_close: 9.64, current_price: 12.85, gap_percent: 33.3 / 100, volume: 4_820_000, has_news: true,
    newest_headline_at: at, catalyst_headline: headline, catalyst_url: null, catalyst_source: 'GlobeNewswire',
  };
}

function feed() {
  return makeLiveScannerFeedStub({
    gappers: [
      row('GRML', 33.3, 12.85, { volume: 4_820_000, rel_volume: 6.4, float: 8_200_000, has_news: true, newest_headline_at: '2026-09-22T12:31:00Z' }),
      row('VXTL', 21.7, 6.91),
      row('BRNQ', -18.9, null, { exchange: 'OTC', has_news: true, newest_headline_at: '2026-09-22T11:58:00Z' }),
    ],
    losers: [row('CBRX', -5.4, 0.94)],
    catalysts: [catalyst('GRML', 'GRML reports positive topline results from Phase 2 study', '2026-09-22T12:31:00Z')],
  });
}

function baseProps(overrides: Partial<DeskBoardProps> = {}): DeskBoardProps {
  return {
    feed: feed(),
    list: 'gappers',
    onListChange: vi.fn(),
    selectedSymbol: 'GRML',
    recordingSymbols: ['GRML'],
    isAllowed: (s: string) => ['GRML', 'BRNQ'].includes(s.toUpperCase()),
    liveTabs: ['GRML'],
    onOpen: vi.fn(),
    onPopOut: vi.fn(),
    onRecord: vi.fn(),
    onAllowlist: vi.fn(),
    ...overrides,
  };
}

afterEach(cleanup);

describe('DeskBoard column contract (issue #276 lock, compact set)', () => {
  it('declares an explicit width role for every board column and pins every width but the flex remainder', () => {
    const declared = new Set(Object.keys(SCANNER_COL_ROLE));
    const undeclared = DESK_BOARD_COLUMNS.map(([key]) => key).filter(key => !declared.has(key));
    expect(undeclared, `board columns with no width role: ${undeclared.join(', ')}`).toEqual([]);
    const css = readFileSync(resolve(here, './deskBoard.css'), 'utf8');
    for (const [key] of DESK_BOARD_COLUMNS) {
      if (key === DESK_BOARD_FLEX_COLUMN) continue;
      expect(css, `deskBoard.css must pin .scanner-col--${key}`).toMatch(new RegExp(`\\.scanner-col--${key}\\s*\\{[^}]*width:`));
    }
    expect(SCANNER_COL_ROLE[DESK_BOARD_FLEX_COLUMN]).toBe('flex');
  });

  it('renders through the shared scanner shell and colgroup, never a second table implementation', () => {
    const src = readFileSync(resolve(here, './DeskBoard.tsx'), 'utf8');
    expect(src).toContain('SCANNER_TABLE_WRAPPER_CLASS');
    expect(src).toContain('ScannerColGroup');
    expect(src.includes("'table-wrapper")).toBe(false);
    render(<DeskBoard {...baseProps()} />);
    const wrapper = screen.getByTestId('desk-board').querySelector('.desk-board__table')!;
    for (const cls of SCANNER_TABLE_WRAPPER_CLASS.split(' ')) expect(wrapper.classList.contains(cls)).toBe(true);
    const cols = wrapper.querySelectorAll('colgroup col');
    expect(cols).toHaveLength(DESK_BOARD_COLUMNS.length + 1);
    const heads = Array.from(wrapper.querySelectorAll('thead th[data-col]')).map(th => th.getAttribute('data-col'));
    expect(heads).toEqual(DESK_BOARD_COLUMNS.map(([key]) => key));
    expect(wrapper.querySelector('thead th')!.textContent).toBe('#');
  });
});

describe('DeskBoard', () => {
  it('opens a row in place on click / Enter and pops it out on double-click', () => {
    const props = baseProps();
    render(<DeskBoard {...props} />);
    fireEvent.click(screen.getByTestId('desk-board-row-VXTL'));
    expect(props.onOpen).toHaveBeenCalledWith('VXTL');
    expect(props.onPopOut).not.toHaveBeenCalled();
    fireEvent.doubleClick(screen.getByTestId('desk-board-row-VXTL'));
    expect(props.onPopOut).toHaveBeenCalledWith('VXTL');
    fireEvent.keyDown(screen.getByTestId('desk-board-row-BRNQ'), { key: 'Enter' });
    expect(props.onOpen).toHaveBeenLastCalledWith('BRNQ');
    expect(screen.getByTestId('desk-board-row-GRML').getAttribute('aria-selected')).toBe('true');
    expect(screen.getByTestId('desk-board-row-VXTL').getAttribute('aria-selected')).toBe('false');
  });

  it('shows REC and bot dots from the recorder and the allowlist: filled when held, hollow when quiet', () => {
    render(<DeskBoard {...baseProps()} />);
    expect(screen.getByTestId('desk-board-rec-GRML')).toBeTruthy();
    expect(screen.getByTestId('desk-board-bot-GRML').getAttribute('data-held')).toBe('1');
    // Allowlisted, no recording and no live tab: hollow, quiet.
    expect(screen.queryByTestId('desk-board-rec-BRNQ')).toBeNull();
    expect(screen.getByTestId('desk-board-bot-BRNQ').getAttribute('data-held')).toBe('0');
    expect(screen.queryByTestId('desk-board-rec-VXTL')).toBeNull();
    expect(screen.queryByTestId('desk-board-bot-VXTL')).toBeNull();
  });

  it('renders the figures honestly: gap bar scaled to the top row, dashes for unknowns, chip + Eastern time', () => {
    render(<DeskBoard {...baseProps()} />);
    expect(screen.getByTestId('desk-board-bar-GRML').style.width).toBe('100%');
    expect(screen.getByTestId('desk-board-bar-VXTL').style.width).toBe('65%');
    expect(screen.getByTestId('desk-board-bar-BRNQ').style.width).toBe('57%');
    const grml = screen.getByTestId('desk-board-row-GRML');
    expect(grml.textContent).toContain('+33.3%');
    expect(grml.textContent).toContain('4.8M');
    expect(grml.textContent).toContain('6.4×');
    expect(grml.textContent).toContain('8.2M');
    expect(grml.textContent).toContain('PR');
    expect(grml.textContent).toContain('08:31');
    const vxtl = screen.getByTestId('desk-board-row-VXTL');
    expect(vxtl.textContent).toContain('+21.7%');
    expect(vxtl.textContent).toContain('no headline');
    expect(vxtl.querySelectorAll('.scanner-col--rel_volume')[0].textContent).toBe('—');
    expect(vxtl.querySelectorAll('.scanner-col--float')[0].textContent).toBe('—');
    // No quote yet is a dash, never 0.00 (ADR 010).
    expect(screen.getByTestId('desk-board-price-BRNQ').textContent).toBe('—');
    expect(screen.getByTestId('desk-board-row-BRNQ').textContent).toContain('−18.9%');
    // Halt state is not carried by the rows: a stated absence with the reason.
    expect(grml.querySelector('.desk-board__state .desk-board__none')!.getAttribute('title')).toMatch(/not carried by the scanner rows/);
  });

  it('the headline line follows the selected row and states its absences', () => {
    const view = render(<DeskBoard {...baseProps()} />);
    let line = screen.getByTestId('desk-board-headline');
    expect(line.textContent).toContain('08:31');
    expect(line.textContent).toContain('GRML reports positive topline results');
    expect(line.textContent).toContain('GlobeNewswire');
    view.rerender(<DeskBoard {...baseProps({ selectedSymbol: 'VXTL' })} />);
    line = screen.getByTestId('desk-board-headline');
    expect(line.textContent).toBe('VXTLno headline');
    view.rerender(<DeskBoard {...baseProps({ selectedSymbol: 'BRNQ' })} />);
    expect(screen.getByTestId('desk-board-headline').textContent).toContain('headline at 07:58 · text is not in the scanner feed');
    view.rerender(<DeskBoard {...baseProps({ selectedSymbol: null })} />);
    expect(screen.getByTestId('desk-board-headline').textContent).toMatch(/Click a row to open it beside the board/);
  });

  it('the list picker offers the registry tab modules and switches the rows; absences are stated', () => {
    const props = baseProps();
    const view = render(<DeskBoard {...props} />);
    const pick = screen.getByTestId('desk-board-pick') as HTMLSelectElement;
    const titles = Array.from(pick.options).map(o => o.textContent);
    expect(titles).toContain('Gappers');
    expect(titles).toContain('HOD Momo');
    expect(titles).toContain('Watchlist');
    expect(screen.getByTestId('desk-board-list-label').textContent).toBe('Gappers');
    expect(screen.getByTestId('desk-board-count').textContent).toBe('3');
    fireEvent.change(pick, { target: { value: 'losers' } });
    expect(props.onListChange).toHaveBeenCalledWith('losers');
    view.rerender(<DeskBoard {...props} list="losers" />);
    expect(screen.getByTestId('desk-board-list-label').textContent).toBe('Losers');
    expect(screen.getByTestId('desk-board-row-CBRX')).toBeTruthy();
    expect(screen.queryByTestId('desk-board-row-GRML')).toBeNull();
    view.rerender(<DeskBoard {...props} list="gainers" />);
    expect(screen.getByTestId('desk-board-absent').textContent).toBe('Gainers: no rows right now');
    view.rerender(<DeskBoard {...props} list="hod_momo" />);
    expect(screen.getByTestId('desk-board-absent').textContent).toMatch(/HOD Momo is not mirrored on the Desk yet/);
    view.rerender(<DeskBoard {...props} list="hod_momo" feed={null} />);
    expect(screen.getByTestId('desk-board-absent').textContent).toBe('No scanner feed in this window');
  });

  it('hover actions call the capture and allowlist commands without opening the row', () => {
    const props = baseProps();
    render(<DeskBoard {...props} />);
    fireEvent.click(screen.getByTestId('desk-board-record-GRML'));
    expect(props.onRecord).toHaveBeenCalledWith('GRML', false);
    expect(screen.getByTestId('desk-board-record-GRML').getAttribute('aria-label')).toBe('Stop rec');
    fireEvent.click(screen.getByTestId('desk-board-record-VXTL'));
    expect(props.onRecord).toHaveBeenCalledWith('VXTL', true);
    expect(screen.getByTestId('desk-board-record-VXTL').getAttribute('aria-label')).toBe('Record');
    fireEvent.click(screen.getByTestId('desk-board-allowlist-BRNQ'));
    expect(props.onAllowlist).toHaveBeenCalledWith('BRNQ', false);
    expect(screen.getByTestId('desk-board-allowlist-BRNQ').getAttribute('aria-label')).toBe('Unlist');
    fireEvent.click(screen.getByTestId('desk-board-allowlist-VXTL'));
    expect(props.onAllowlist).toHaveBeenCalledWith('VXTL', true);
    expect(screen.getByTestId('desk-board-allowlist-VXTL').getAttribute('aria-label')).toBe('Allowlist');
    expect(props.onOpen).not.toHaveBeenCalled();
  });

  it('names each hover action by its full label and carries the short one for the narrow board (QA V37)', () => {
    render(<DeskBoard {...baseProps()} />);
    const stopRec = screen.getByRole('button', { name: 'Stop rec' });
    expect(stopRec.getAttribute('data-testid')).toBe('desk-board-record-GRML');
    const short = stopRec.querySelector('.desk-board__act-text--short');
    expect(short?.textContent).toBe('Stop');
    expect(short?.getAttribute('aria-hidden')).toBe('true');
    const allow = screen.getByTestId('desk-board-allowlist-VXTL');
    expect(allow.querySelector('.desk-board__act-text:not(.desk-board__act-text--short)')?.textContent).toBe('Allowlist');
    expect(allow.querySelector('.desk-board__act-text--short')?.textContent).toBe('Allow');
    expect(screen.getAllByRole('button', { name: 'Record' }).length).toBe(2);
  });

  it('the footer counts shown of total, says when the exchange filter hides rows, and names the freeze only for Gappers', () => {
    const props = baseProps({ filterRows: rows => rows.filter(r => r.exchange !== 'OTC') });
    const view = render(<DeskBoard {...props} />);
    let foot = screen.getByTestId('desk-board-foot');
    expect(foot.textContent).toContain('2 of 3');
    expect(foot.textContent).toContain('1 hidden by the exchange filter');
    expect(foot.textContent).toContain('board freezes at the open');
    expect(foot.textContent).toContain('recording');
    expect(foot.textContent).toContain('allowlisted, depth line held');
    expect(foot.textContent).toContain('allowlisted, quiet');
    expect(screen.queryByTestId('desk-board-row-BRNQ')).toBeNull();
    view.rerender(<DeskBoard {...props} list="losers" />);
    foot = screen.getByTestId('desk-board-foot');
    expect(foot.textContent).toContain('1 of 1');
    expect(foot.textContent).not.toContain('board freezes at the open');
    expect(foot.textContent).not.toContain('hidden by the exchange filter');
  });
});
