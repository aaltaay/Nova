/** Fetches journal calendar aggregates for the Reports tab. */
import { useEffect, useRef, useState } from 'react';
import { API_BASE_URL, JOURNAL_POLL_INTERVAL_MS } from '../constants';
import type { MonthCalendarResponse, YearCalendarResponse } from './types';

const JOURNAL_API = `${API_BASE_URL}/api/journal`;

export interface UseCalendarReturn {
  yearData: YearCalendarResponse | null;
  monthData: MonthCalendarResponse | null;
  loading: boolean;
  error: string | null;
}

export function useCalendar(
  enabled: boolean,
  year: number,
  month: number | null,
  includeMock: boolean,
): UseCalendarReturn {
  const [yearData, setYearData] = useState<YearCalendarResponse | null>(null);
  const [monthData, setMonthData] = useState<MonthCalendarResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const inFlight = useRef(false);

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;

    async function poll() {
      if (inFlight.current) return;
      inFlight.current = true;
      try {
        const mockQ = includeMock ? '&include_mock=true' : '';
        const yearRes = await fetch(`${JOURNAL_API}/calendar?year=${year}${mockQ}`);
        if (!yearRes.ok) throw new Error(`HTTP ${yearRes.status}`);
        const yearJson = (await yearRes.json()) as YearCalendarResponse;

        let monthJson: MonthCalendarResponse | null = null;
        if (month != null) {
          const monthRes = await fetch(
            `${JOURNAL_API}/calendar?year=${year}&month=${month}${mockQ}`,
          );
          if (!monthRes.ok) throw new Error(`HTTP ${monthRes.status}`);
          monthJson = (await monthRes.json()) as MonthCalendarResponse;
        }

        if (!cancelled) {
          setYearData(yearJson);
          setMonthData(monthJson);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load calendar');
        }
      } finally {
        inFlight.current = false;
        if (!cancelled) setLoading(false);
      }
    }

    setLoading(true);
    poll();
    const interval = setInterval(poll, JOURNAL_POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [enabled, year, month, includeMock]);

  return { yearData, monthData, loading, error };
}
