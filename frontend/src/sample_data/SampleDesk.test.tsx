/**
 * @vitest-environment jsdom
 *
 * #449: the Desk on the sample desk shows the sample board, opens its rows in
 * the sample workspace, keeps its list and its watch list in memory, and
 * locks the actions it cannot take -- each with its reason.
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  ModuleVisibilityProvider,
  useWorkspace,
  WorkspaceValueProvider,
  type WorkspaceValue,
} from '../workspace';
import { resetWatchListForTests } from '../watch_list/watchListStore';
import { SAMPLE_DESK_ALLOWLIST_WHY, SAMPLE_DESK_RECORD_WHY } from './sampleCopy';
import { SampleDataProvider } from './SampleDataContext';
import { SampleDesk } from './SampleDesk';
import { SampleWorkspaceProvider } from './SampleWorkspaceProvider';

vi.mock('../hod_momo/HodMomoDock', () => ({ HodMomoDock: () => <div data-testid="hod-momo-dock" /> }));

let root: Root;
let container: HTMLDivElement;
let ws: WorkspaceValue;
let writes: string[];

function Probe() {
  ws = useWorkspace();
  return null;
}

const q = <T extends Element = HTMLElement>(testId: string) =>
  container.querySelector(`[data-testid="${testId}"]`) as T | null;

beforeEach(() => {
  window.history.replaceState({}, '', '/?view=sample');
  writes = [];
  vi.spyOn(Storage.prototype, 'setItem').mockImplementation((key: string) => { writes.push(key); });
  container = document.createElement('div');
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => {
    root.render(
      <SampleDataProvider>
        <WorkspaceValueProvider value={{ deskVenue: 'paper' } as WorkspaceValue}>
          <SampleWorkspaceProvider>
            <ModuleVisibilityProvider>
              <SampleDesk />
              <Probe />
            </ModuleVisibilityProvider>
          </SampleWorkspaceProvider>
        </WorkspaceValueProvider>
      </SampleDataProvider>,
    );
  });
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  vi.restoreAllMocks();
  window.history.replaceState({}, '', '/');
});

describe('SampleDesk', () => {
  it('shows the sample board, never "not available"', () => {
    expect(q('desk-page')?.textContent).not.toMatch(/not available/i);
    expect(q('desk-board')).toBeTruthy();
    expect(q('desk-board-row-SMPL')).toBeTruthy();
    expect(q('hod-momo-dock')).toBeTruthy();
    expect(q('desk-workspace-empty')).toBeTruthy();
  });

  it('a row click opens the symbol beside the board; a double-click opens the full Trader', () => {
    act(() => q('desk-board-row-SMPL')?.click());
    expect(ws.traderTabs).toEqual(['SMPL']);
    expect(ws.traderViewActive).toBe(false);
    expect(q('desk-workspace-empty')).toBeNull();
    act(() => { q('desk-board-row-GAPX')?.dispatchEvent(new MouseEvent('dblclick', { bubbles: true })); });
    expect(ws.activeTraderSymbol).toBe('GAPX');
    expect(ws.traderViewActive).toBe(true);
  });

  it('keeps the board list in memory', () => {
    const pick = q<HTMLSelectElement>('desk-board-pick')!;
    act(() => {
      pick.value = 'gainers';
      pick.dispatchEvent(new Event('change', { bubbles: true }));
    });
    expect(q('desk-board-list-label')?.textContent).toBe('Gainers');
    expect(q('desk-board-row-RUNR')).toBeTruthy();
    expect(writes).toEqual([]);
  });

  it("Watch works on the sample desk's own list, in memory", () => {
    const watch = q<HTMLButtonElement>('desk-board-watch-SMPL')!;
    expect(watch.disabled).toBe(false);
    act(() => watch.click());
    expect(q('desk-board-watch-SMPL')?.getAttribute('aria-pressed')).toBe('true');
    expect(writes).toEqual([]);
    act(() => watch.click());
    resetWatchListForTests();
  });

  it('locks Record and Allowlist, each with its reason', () => {
    const cases: [string, string][] = [
      ['desk-board-record-SMPL', SAMPLE_DESK_RECORD_WHY],
      ['desk-board-allowlist-SMPL', SAMPLE_DESK_ALLOWLIST_WHY],
    ];
    for (const [testId, why] of cases) {
      const button = q<HTMLButtonElement>(testId)!;
      expect(button.disabled, testId).toBe(true);
      expect(button.dataset.why, testId).toBe(why);
      act(() => button.click());
    }
    expect(writes).toEqual([]);
    expect(ws.traderTabs).toEqual([]);
  });
});
