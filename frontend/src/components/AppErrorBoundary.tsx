import { Component, type ErrorInfo, type ReactNode } from 'react';
import { reportClientError } from '../utils/reportClientError';

interface Props {
  children: ReactNode;
  /** Optional label for logs (e.g. dashboard | stock-view). */
  source?: string;
}

interface State {
  error: Error | null;
}

/** App-level boundary — keeps one React subtree crash from blanking the whole UI. */
export class AppErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error('[Nova] App error boundary', error, info.componentStack);
    reportClientError({
      message: error.message || String(error),
      stack: error.stack,
      componentStack: info.componentStack,
      source: this.props.source || 'react-boundary',
    });
  }

  render(): ReactNode {
    if (!this.state.error) return this.props.children;
    return (
      <div className="empty-state" role="alert">
        <p>Something went wrong in this view. The rest of Nova may still work.</p>
        <p className="na-muted">{this.state.error.message}</p>
        <button type="button" className="history-banner-btn" onClick={() => this.setState({ error: null })}>
          Retry
        </button>
      </div>
    );
  }
}
