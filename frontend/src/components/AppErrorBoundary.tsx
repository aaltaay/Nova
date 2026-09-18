import { Component, type ErrorInfo, type ReactNode } from 'react';
import { reportClientError } from '../utils/reportClientError';
import {
  clearShellAutoReloadSlot,
  consumeShellAutoReloadSlot,
  shouldAutoReloadShell,
} from './appErrorRecovery';

interface Props {
  children: ReactNode;
  /** Optional label for logs (e.g. dashboard | stock-view). */
  source?: string;
}

interface State {
  error: Error | null;
  remountKey: number;
  recovering: boolean;
}

/**
 * App-level boundary — keeps one React subtree crash from blanking the whole UI.
 * Fatal provider/hook errors (often Vite HMR context skew) auto hard-reload once.
 */
export class AppErrorBoundary extends Component<Props, State> {
  state: State = { error: null, remountKey: 0, recovering: false };

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { error };
  }

  componentDidMount(): void {
    if (!this.state.error) clearShellAutoReloadSlot();
  }

  componentDidUpdate(_prev: Props, prevState: State): void {
    if (prevState.error && !this.state.error) clearShellAutoReloadSlot();
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error('[Nova] App error boundary', error, info.componentStack);
    reportClientError({
      message: error.message || String(error),
      stack: error.stack,
      componentStack: info.componentStack,
      source: this.props.source || 'react-boundary',
    });

    if (shouldAutoReloadShell(this.props.source, error) && consumeShellAutoReloadSlot()) {
      this.setState({ recovering: true });
      window.setTimeout(() => {
        window.location.reload();
      }, 80);
    }
  }

  private handleRetry = (): void => {
    const { error } = this.state;
    if (shouldAutoReloadShell(this.props.source, error)) {
      window.location.reload();
      return;
    }
    this.setState((s) => ({
      error: null,
      recovering: false,
      remountKey: s.remountKey + 1,
    }));
  };

  render(): ReactNode {
    const { error, remountKey, recovering } = this.state;
    if (error) {
      return (
        <div className="empty-state" role="alert">
          {recovering ? (
            <p>Recovering — reloading Nova…</p>
          ) : (
            <>
              <p>Something went wrong in this view. The rest of Nova may still work.</p>
              <p className="na-muted">{error.message}</p>
              <button
                type="button"
                className="history-banner-btn"
                onClick={this.handleRetry}
              >
                {shouldAutoReloadShell(this.props.source, error) ? 'Reload Nova' : 'Retry'}
              </button>
            </>
          )}
        </div>
      );
    }
    // Named host so Stock View's body/#root flex column can stretch through
    // nested boundaries (plain divs collapse to content height and steal clicks).
    return (
      <div key={remountKey} className="app-shell-host">
        {this.props.children}
      </div>
    );
  }
}
