import { Profiler, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { getHotListState, hotListActions, useHotList } from '../../src/hot_list';
import { TopOfBookProvider, useTopOfBook } from '../../src/hotkeys/TopOfBookContext';
import { DepthLadder } from '../../src/ibkr/DepthLadder';
import { viewLockReason, viewStampFor } from '../../src/market_view';
import type { DepthMarker } from '../../src/ibkr/depthMarkers';
import './deskFreezeFixtureTypes';
import '../../src/index.css';

const metrics = { hotCommits: 0, depthCommits: 0 };
window.deskFreezeFixture = {
  metrics, hotState: getHotListState,
  stamp: () => viewStampFor('FIXTURE', Date.now()),
  lock: () => viewLockReason('FIXTURE'),
};

const markers: DepthMarker[] = [
  { id: 'entry', price: 10, label: 'ENTRY', color: '#aaa', working: false, rests: 'bid', tip: 'Entry plan' },
  { id: 'stop', price: 9.95, label: 'STOP', color: '#f55', working: true, rests: 'bid', tip: 'Working stop' },
  { id: 'target', price: 10.06, label: 'TARGET', color: '#5f5', working: false, rests: 'ask', tip: 'Target plan' },
];

function HotListReader() {
  const state = useHotList();
  return <output data-testid="hot-list-view">{JSON.stringify(state)}</output>;
}

/** Observe the real context clear without making the rest of the fixture a top-of-book subscriber. */
function DepthCommitBarrier({ active }: { active: boolean }) {
  const { topOfBook } = useTopOfBook();
  return <output data-testid="depth-paint-state" hidden>
    {active ? 'visible' : topOfBook === null ? 'hidden' : 'hiding'}
  </output>;
}

function Fixture() {
  const [active, setActive] = useState(true);
  return (
    <main style={{ padding: 20, color: 'white' }}>
      <button onClick={() => setActive(value => !value)}>{active ? 'Hide depth' : 'Show depth'}</button>
      <button onClick={() => { void hotListActions.refresh(); }}>Refresh hot list</button>
      <Profiler id="hot-list" onRender={() => { metrics.hotCommits += 1; }}>
        <HotListReader />
      </Profiler>
      <DepthCommitBarrier active={active} />
      <section style={{ width: 720, height: 460, visibility: active ? 'visible' : 'hidden' }}>
        <Profiler id="depth" onRender={() => { metrics.depthCommits += 1; }}>
          <DepthLadder symbol="FIXTURE" uiActive={active} markers={markers} traderTab />
        </Profiler>
      </section>
    </main>
  );
}

createRoot(document.getElementById('root')!).render(<TopOfBookProvider><Fixture /></TopOfBookProvider>);
