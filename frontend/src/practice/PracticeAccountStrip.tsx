/**
 * Header strip for Nova's practice account (ADR 020): account id, cash, buying
 * power, day P&L and fees today, plus the replay key on Sim. Renders nothing
 * off the practice venues -- there is no practice account to show there.
 */
import {
  PRACTICE_STRIP_LOADING,
  PRACTICE_STRIP_REPLAY_LABEL,
  PRACTICE_STRIP_UNAVAILABLE,
} from '../constantGroups/practice';
import { buildPracticeAccountView, isPracticeVenue, type PracticeMetricView } from './practiceAccountModel';
import { usePracticeAccount } from './practiceAccountResource';

function Metric({ metric, testId }: { metric: PracticeMetricView; testId: string }) {
  return (
    <span className="global-app-bar__metric practice-strip__metric" title={metric.title} data-testid={testId}>
      <label>{metric.label}</label>
      <span className={metric.tone}>{metric.value}</span>
    </span>
  );
}

export function PracticeAccountStrip({ venue }: { venue: string | null | undefined }) {
  const { data, error } = usePracticeAccount(venue);
  if (!isPracticeVenue(venue)) return null;
  if (!data || data.venue !== venue) {
    const unavailable = Boolean(error);
    return (
      <span
        className={`global-app-bar__cluster practice-strip practice-strip--${unavailable ? 'unavailable' : 'loading'}`}
        data-testid="practice-strip"
        data-venue={venue}
        data-state={unavailable ? 'unavailable' : 'loading'}
        title={unavailable ? `${PRACTICE_STRIP_UNAVAILABLE}: ${error}` : PRACTICE_STRIP_LOADING}
      >
        <span className="global-app-bar__offline-chip">
          {unavailable ? PRACTICE_STRIP_UNAVAILABLE : PRACTICE_STRIP_LOADING}
        </span>
      </span>
    );
  }
  const view = buildPracticeAccountView(data);
  return (
    <span
      className="global-app-bar__cluster practice-strip"
      data-testid="practice-strip"
      data-venue={venue}
      data-state="ready"
    >
      <span className="practice-strip__account" title={view.accountTitle} data-testid="practice-strip-account">
        {view.accountId}
      </span>
      <span className="global-app-bar__sep" aria-hidden />
      <Metric metric={view.cash} testId="practice-strip-cash" />
      <Metric metric={view.buyingPower} testId="practice-strip-bp" />
      <Metric metric={view.dayPnl} testId="practice-strip-day-pnl" />
      <Metric metric={view.fees} testId="practice-strip-fees" />
      {view.replay && (
        <span
          className={`global-app-bar__metric practice-strip__metric practice-strip__replay${view.replay.loaded ? '' : ' is-empty'}`}
          title={view.replay.title}
          data-testid="practice-strip-replay"
        >
          <label>{PRACTICE_STRIP_REPLAY_LABEL}</label>
          <span>{view.replay.value}</span>
        </span>
      )}
    </span>
  );
}
