/**
 * Reports tab -- TraderVue-style P&L calendar from journal trades + file import.
 *
 * Hosted on the Account page it follows the page's venue and its All / You / Bots pick (ADR 069 decision 6,
 * mockup reports-v1): Paper reads Paper's round trips, one per holder, with yours and the bots' beside each total
 * on All, and its Import row says an import is Live's. Live and Sim -- and any other host -- read the journal as
 * it was.
 */
import { useEffect, useState } from 'react';
import { AnalyticsSummary } from './AnalyticsSummary';
import { REPORTS_IMPORT_ON_LIVE, REPORTS_SOURCE_NOTE_PAPER, reportsEmptyPaper } from './booksConstants';
import { REPORTS_SOURCE_NOTE } from './importConstants';
import { DrawdownPanel } from './DrawdownPanel';
import { MonthDetail } from './MonthDetail';
import { ReportsImport } from './ReportsImport';
import { RMultiplesPanel } from './RMultiplesPanel';
import { botCounts, journalViewQuery, readsBooks, type ReportsHost } from './reportsView';
import { TagPerformance } from './TagPerformance';
import { YearCalendar } from './YearCalendar';
import { useCalendar } from './useCalendar';
import { useReportsV2 } from './useReportsV2';

export function ReportsTab({ venue, view, onBotCounts }: Partial<ReportsHost> = {}) {
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [openMonth, setOpenMonth] = useState<number | null>(null);
  const [includeMock, setIncludeMock] = useState(false);
  const [refreshToken, setRefreshToken] = useState(0);
  const books = readsBooks(venue);
  const viewQuery = journalViewQuery(venue, view);

  const { yearData, monthData, loading, error } = useCalendar(
    true,
    year,
    openMonth,
    includeMock,
    refreshToken,
    viewQuery,
  );
  const reportsV2 = useReportsV2(true, includeMock, refreshToken, viewQuery);
  // The Bots menu counts the year shown, whatever the pick; a new pick's load keeps the last counts.
  useEffect(() => {
    if (!books) onBotCounts?.(null);
    else if (yearData) onBotCounts?.(botCounts(yearData.holders));
  }, [onBotCounts, books, yearData]);

  return (
    <div className="reports-panel journal-panel" data-venue={venue}>
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

      {/* Two calendars, two sources -- say which this one is (QA V42). */}
      <p className="reports-source-note" data-testid="reports-source-note">
        {books ? REPORTS_SOURCE_NOTE_PAPER : REPORTS_SOURCE_NOTE}
      </p>

      {books ? (
        <p className="reports-import reports-import-elsewhere" data-testid="reports-import-on-live">
          {REPORTS_IMPORT_ON_LIVE}
        </p>
      ) : (
        <ReportsImport onImported={() => setRefreshToken(n => n + 1)} />
      )}

      {includeMock && (
        <div className="journal-demo-banner">
          Demo data is on -- calendar includes mock journal trades. Real metrics stay separate unless you leave this checked.
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
          {books
            ? reportsEmptyPaper(year)
            : `No closed trades in ${year}. Import a CSV/JSON file, enable demo data, or close trades into the journal.`}
        </div>
      )}

      {reportsV2.error && (
        <div className="reports-status reports-error">{reportsV2.error}</div>
      )}
      <div className="reports-v2-stack">
        <TagPerformance data={reportsV2.tags} loading={reportsV2.loading} books={books} />
        <RMultiplesPanel data={reportsV2.rMultiples} loading={reportsV2.loading} books={books} />
        <DrawdownPanel data={reportsV2.drawdown} loading={reportsV2.loading} books={books} />
      </div>
    </div>
  );
}
