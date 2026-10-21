/** The Trader toolbar's Ahead switch (ADR 065): off by default, kept per viewer and the same in every window. While it is
 * off the desk asks nothing. On with no 1-minute pane on the tab, it says Ahead draws there. */
import { useStockReadContext } from '../stock_read';
import { useAheadSceneOf } from './AheadChartLayer';
import { AHEAD_WORDS } from './aheadConstants';
import { setAheadPrefs, useAheadPrefs } from './aheadPrefs';
import './ahead.css';

export function AheadToolbar() {
  const prefs = useAheadPrefs();
  const symbol = useStockReadContext()?.symbol ?? '';
  const scene = useAheadSceneOf(symbol);
  const noPane = prefs.shown && symbol !== '' && scene === null;
  return (
    <>
      <button
        type="button"
        className={`chart-grid__optional-toggle ahead-toggle${prefs.shown ? ' ahead-toggle--on' : ''}`}
        aria-pressed={prefs.shown}
        title={noPane ? `${AHEAD_WORDS.toggleTitle} ${AHEAD_WORDS.onlyOneMinute}` : AHEAD_WORDS.toggleTitle}
        onClick={() => setAheadPrefs({ shown: !prefs.shown })}
        data-testid="ahead-toggle"
      >
        <span className="ahead-toggle__glyph" aria-hidden="true" />
        {AHEAD_WORDS.toggleLabel}
        <span className="ahead-toggle__badge">{AHEAD_WORDS.newBadge}</span>
      </button>
      {noPane && <span className="ahead-toggle__note" data-testid="ahead-no-pane">{AHEAD_WORDS.onlyOneMinute}</span>}
    </>
  );
}
