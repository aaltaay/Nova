/** The Trader toolbar's Heat map switch (ADR 061): one click swaps the four charts for the heat map, one click back. */
import { setHeatPrefs, useHeatPrefs } from './heatMapPrefs';
import { HEAT_BACK_TITLE, HEAT_TOGGLE_LABEL, HEAT_TOGGLE_TITLE } from './heatMapConstants';
import './heatMap.css';

export function HeatMapToolbar({ testId = 'heat-map-toggle' }: { testId?: string }) {
  const { shown } = useHeatPrefs();
  return (
    <button
      type="button"
      className={`chart-grid__optional-toggle heat-toggle${shown ? ' heat-toggle--on' : ''}`}
      aria-pressed={shown}
      title={shown ? HEAT_BACK_TITLE : HEAT_TOGGLE_TITLE}
      onClick={() => setHeatPrefs({ shown: !shown })}
      data-testid={testId}
    >
      <span className="heat-toggle__glyph" aria-hidden="true" />
      {HEAT_TOGGLE_LABEL}
    </button>
  );
}

/** Whether the Trader shows the heat map in place of its charts. */
export function useHeatMapShown(): boolean {
  return useHeatPrefs().shown;
}
