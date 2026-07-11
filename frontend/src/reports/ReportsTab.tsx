/** Reports tab — TraderVue-style P&L calendar from journal trades (no import). */
import { useState } from 'react';
import { AnalyticsSummary } from './AnalyticsSummary';
import { MonthDetail } from './MonthDetail';
import { YearCalendar } from './YearCalendar';
import { useCalendar } from './useCalendar';

export function ReportsTab() {
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [openMonth, setOpenMonth] = useState<number | null>(null);
  const [includeMock, setIncludeMock] = useState(false);

  const { yearData, monthData, loading, error } = useCalendar(
    true,
    year,
    openMonth,
    includeMock,
  );

  return (
    <div className="reports-panel journal-panel">
      <div className="reports-toolbar">
        <h2 className="reports-title">Reports</h2>
        <div className="reports-toolbar-controls">
          <label className="journal-demo-toggle" title="Include synthetic journal rows tagged is_mock.">
            <input
              type="checkbox"
              checked={includeMock}
              onChange={e => setIncludeMock(e.target.checked)}
            />
            Show demo data
          </label>
          <div className="reports-year-nav">
            <button type="button" onClick={() => setYear(y => y - 1)} aria-label="Previous year">
              ‹
            </button>
            <span className="reports-year-label">{year}</span>
            <button type="button" onClick={() => setYear(y => y + 1)} aria-label="Next year">
              ›
            </button>
          </div>
        </div>
      </div>

      {includeMock && (
        <div className="journal-demo-banner">
          Demo data is on — calendar includes mock journal trades. Real metrics stay separate unless you leave this checked.
        </div>
      )}

      {loading && !yearData && <div className="reports-status">Loading calendar…</div>}
      {error && <div className="reports-status reports-error">{error}</div>}

      {yearData && (
        <>
          <AnalyticsSummary data={yearData} />
          {openMonth != null && monthData && (
            <MonthDetail data={monthData} onClose={() => setOpenMonth(null)} />
          )}
          <YearCalendar
            months={yearData.months}
            year={year}
            openMonth={openMonth}
            onOpenMonth={m => setOpenMonth(prev => (prev === m ? null : m))}
          />
        </>
      )}

      {!loading && yearData && yearData.year_trade_count === 0 && (
        <div className="reports-empty">
          No closed trades in {year}. Enable demo data, or close trades into the journal to populate the calendar.
        </div>
      )}
    </div>
  );
}
