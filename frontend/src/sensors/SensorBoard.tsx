import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  SENSORS_BOARD_HINT,
  SENSORS_BOARD_TITLE,
  SENSORS_DEFAULT_LIQUID,
  SENSORS_EMPTY_CATALOG,
  SENSORS_LOAD_ERROR,
  SENSORS_POLL_MS,
  SENSORS_REFRESH_LABEL,
  SENSORS_SIM_SYMBOL,
  SENSORS_SYMBOL_LABEL,
} from '../constantGroups/sensors';
import { fetchSensorCatalog, fetchSensorSnapshot } from '../api/sensorApi';
import { useIbkrStatus } from '../ibkr/useIbkrStatus';
import { SensorStatusChip } from './SensorStatusChip';
import { sensorSummary } from './sensorSummary';
import type { SensorCatalogRow, SensorEnvelope } from './types';

function mergeRows(catalog: SensorCatalogRow[], readings: SensorEnvelope[]): SensorEnvelope[] {
  const byKey = new Map(readings.map((row) => [row.sensor, row]));
  return catalog.map((item) => {
    const live = byKey.get(item.sensor);
    if (live) return { ...live, title: item.title };
    return {
      sensor: item.sensor,
      title: item.title,
      status: item.status,
      as_of: 0,
      data: {},
      error: SENSORS_EMPTY_CATALOG,
    };
  });
}

export function SensorBoard() {
  const status = useIbkrStatus();
  const defaultSymbol = status.mode === 'sim' ? SENSORS_SIM_SYMBOL : SENSORS_DEFAULT_LIQUID;
  const [symbol, setSymbol] = useState(defaultSymbol);
  const [draft, setDraft] = useState(defaultSymbol);
  const [catalog, setCatalog] = useState<SensorCatalogRow[]>([]);
  const [readings, setReadings] = useState<SensorEnvelope[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setSymbol(defaultSymbol);
    setDraft(defaultSymbol);
  }, [defaultSymbol]);

  const load = useCallback(async (nextSymbol: string) => {
    setLoading(true);
    try {
      const [cat, snap] = await Promise.all([
        fetchSensorCatalog(),
        fetchSensorSnapshot(nextSymbol),
      ]);
      setCatalog(cat.sensors || []);
      setReadings(snap.sensors || []);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : SENSORS_LOAD_ERROR);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load(symbol);
    const id = window.setInterval(() => {
      void load(symbol);
    }, SENSORS_POLL_MS);
    return () => window.clearInterval(id);
  }, [load, symbol]);

  const rows = useMemo(() => mergeRows(catalog, readings), [catalog, readings]);

  return (
    <div className="sensor-board" data-testid="sensor-board">
      <h3 className="settings-block-title">{SENSORS_BOARD_TITLE}</h3>
      <p className="settings-block-hint">{SENSORS_BOARD_HINT}</p>
      <form
        className="sensor-board-toolbar"
        onSubmit={(e) => {
          e.preventDefault();
          const next = draft.trim().toUpperCase() || defaultSymbol;
          setDraft(next);
          setSymbol(next);
        }}
      >
        <label className="sensor-board-symbol">
          <span>{SENSORS_SYMBOL_LABEL}</span>
          <input
            data-testid="sensor-symbol"
            value={draft}
            onChange={(e) => setDraft(e.target.value.toUpperCase())}
            spellCheck={false}
            autoCapitalize="characters"
          />
        </label>
        <button type="submit" className="sensor-board-refresh">
          {SENSORS_REFRESH_LABEL}
        </button>
      </form>
      {error && (
        <div className="sensor-board-error" data-testid="sensor-board-error" role="alert">
          {error}
        </div>
      )}
      {!error && !rows.length && !loading && (
        <div className="sensor-board-empty" data-testid="sensor-board-empty" role="status">
          {SENSORS_EMPTY_CATALOG}
        </div>
      )}
      <ul className="sensor-board-list">
        {rows.map((row) => (
          <li key={row.sensor} className="sensor-board-row" data-testid={`sensor-row-${row.sensor}`}>
            <div className="sensor-board-row-head">
              <span className="sensor-board-name" data-testid={`sensor-title-${row.sensor}`}>
                {row.title || row.sensor}
              </span>
              <SensorStatusChip status={row.status} />
            </div>
            <div
              className={`sensor-board-value${row.error ? ' is-error' : ''}`}
              data-testid={`sensor-value-${row.sensor}`}
            >
              {sensorSummary(row)}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
