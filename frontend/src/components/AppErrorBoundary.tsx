import { Component, type ErrorInfo, type ReactNode } from 'react';
import {
  APP_ERROR_SHELL_MESSAGE,
  APP_ERROR_SHELL_SOURCE,
  APP_ERROR_VIEW_MESSAGE,
} from '../constantGroups/ux';
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

  /** The app-shell card offers a reload, like its copy says (C56). */
  private reloads(): boolean {
    return this.props.source === APP_ERROR_SHELL_SOURCE || shouldAutoReloadShell(this.props.source, this.state.error);
  }

  private handleRetry = (): void => {
    if (this.reloads()) {
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
              <p data-testid="app-error-message">
                {this.props.source === APP_ERROR_SHELL_SOURCE ? APP_ERROR_SHELL_MESSAGE : APP_ERROR_VIEW_MESSAGE}
              </p>
              <p className="na-muted">{error.message}</p>
              <button
                type="button"
                className="history-banner-btn"
                onClick={this.handleRetry}
              >
                {this.reloads() ? 'Reload Nova' : 'Retry'}
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
