import { Component, type ErrorInfo, type ReactNode } from 'react';
import { CHART_CRASH_AUTO_RETRY_MS, CHART_CRASH_AUTO_RETRY_WINDOW_MS } from '../constants';
import { reportClientError } from '../utils/reportClientError';

/** The reason under the headline: one line of the error's own words. */
const REASON_MAX_CHARS = 200;

interface Props {
  children: ReactNode;
  /** The pane (its timeframe), named in the report. */
  label?: string;
}

interface State {
  error: Error | null;
  /** The automatic retry is scheduled. */
  retrying: boolean;
}

export class TickerChartErrorBoundary extends Component<Props, State> {
  state: State = { error: null, retrying: false };

  private retryTimer: number | null = null;
  private lastAutoRetryAt = -Infinity;

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error('[Nova] Ticker chart crashed', this.props.label ?? '', error, info.componentStack);
    reportClientError({
      message: error.message || String(error),
      stack: error.stack,
      componentStack: info.componentStack,
      source: this.props.label ? `ticker-chart:${this.props.label}` : 'ticker-chart',
    });
    // Once, on its own: a pane that crashed on a series caught mid-change draws fine a moment later.
    const now = Date.now();
    if (this.retryTimer === null && now - this.lastAutoRetryAt > CHART_CRASH_AUTO_RETRY_WINDOW_MS) {
      this.lastAutoRetryAt = now;
      this.setState({ retrying: true });
      this.retryTimer = window.setTimeout(() => {
        this.retryTimer = null;
        this.setState({ error: null, retrying: false });
      }, CHART_CRASH_AUTO_RETRY_MS);
    }
  }

  componentWillUnmount(): void {
    if (this.retryTimer !== null) window.clearTimeout(this.retryTimer);
    this.retryTimer = null;
  }

  private retry = (): void => {
    if (this.retryTimer !== null) window.clearTimeout(this.retryTimer);
    this.retryTimer = null;
    this.setState({ error: null, retrying: false });
  };

  render(): ReactNode {
    const { error, retrying } = this.state;
    if (!error) return this.props.children;
    const reason = (error.message || String(error)).trim().slice(0, REASON_MAX_CHARS);
    return (
      <div className="chart-card">
        <div className="chart-overlay chart-overlay--error chart-overlay--crashed" role="alert" data-testid="chart-crashed">
          <span>Chart unavailable. The scanner is still running.</span>
          {reason && <span className="chart-overlay-detail" data-testid="chart-crashed-reason">{reason}</span>}
          {retrying && <span className="chart-overlay-detail">Drawing it again…</span>}
          <button type="button" onClick={this.retry} data-testid="chart-crashed-retry">
            Retry chart
          </button>
        </div>
      </div>
    );
  }
}
