import { Component, type ErrorInfo, type ReactNode } from 'react';
import { reportClientError } from '../utils/reportClientError';

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

export class TickerChartErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error('[Nova] Ticker chart crashed', error, info.componentStack);
    reportClientError({
      message: error.message || String(error),
      stack: error.stack,
      componentStack: info.componentStack,
      source: 'ticker-chart',
    });
  }

  render(): ReactNode {
    if (!this.state.error) return this.props.children;
    return (
      <div className="chart-card">
        <div className="chart-overlay chart-overlay--error">
          Chart unavailable. The scanner is still running.
          <button type="button" onClick={() => this.setState({ error: null })}>
            Retry chart
          </button>
        </div>
      </div>
    );
  }
}
