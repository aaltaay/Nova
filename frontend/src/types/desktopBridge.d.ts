interface Window {
  __NOVA_API_BASE__?: string;
  novaDesktop?: {
    isDesktop: boolean;
    apiBase: string;
    /** Same NOVA_API_KEY the API loaded (D-040 / bot writes). Never log this. */
    apiKey?: string;
    getVersion: () => Promise<string>;
    /** Electron IPC: open Stock View in a child BrowserWindow. */
    openStockView?: (url: string) => Promise<boolean>;
    /** Electron IPC: open (or focus) the one Top 9 pop-up window (top_nine/, `?view=top9`). */
    openTopNine?: (url: string) => Promise<boolean>;
    /** Electron IPC: keep the asking window above the others (the Top 9 pop-up's switch); answers the state. */
    setKeepOnTop?: (on: boolean) => Promise<boolean>;
    /** Electron IPC: raise the asking window (a desk window that just opened a symbol for the pop-up). */
    focusWindow?: () => Promise<boolean>;
    /** Electron IPC: open an allowlisted HTTPS URL in the system browser. */
    openExternal?: (url: string) => Promise<boolean>;
    /** Electron IPC: the followed traders' stream in a small window of its own (followed_traders/stream.ts). */
    openStream?: (videoId: string) => Promise<boolean>;
    /** Electron IPC: Google's sign-in page in its own window, for the stream player (YouTube's bot check). */
    youtubeSignIn?: () => Promise<boolean>;
    /** Called when that window closes, true when it reached YouTube signed in; returns the unsubscribe. */
    onYoutubeSignedIn?: (cb: (signedIn: boolean) => void) => () => void;
    /** Electron IPC: the header mute (sound/) -- every Nova window's audio, the stream's pop-out included. */
    setSoundMuted?: (muted: boolean) => void;
    /** Electron IPC: stop + start the local FastAPI sidecar, then wait for health. */
    /** `from` / `to`: the backend's revision before and after (null when it does not say). */
    restartApi?: () => Promise<{ ok: boolean; error?: string; from?: string | null; to?: string | null }>;
    /** Electron IPC: the update notice and What's new card (desktop_update/). */
    updates?: {
      /** Called with the current view, then every change; returns the unsubscribe. Views are unchecked wire data. */
      subscribe: (onView: (view: unknown) => void) => () => void;
      act: (request: { action: string; url?: string }) => Promise<{ ok: boolean; error?: string }>;
    };
    /** Electron IPC: the trading screen recording's status (screen_record/, ADR 035). Read-only. */
    screenRecord?: {
      /** Called with the current view, then every change; returns the unsubscribe. Views are unchecked wire data. */
      subscribe: (onView: (view: unknown) => void) => () => void;
    };
    /** Electron IPC: share clips (clips/, ADR 039) -- the view, the operator's requests, this window's Trader tab. */
    clips?: {
      /** Called with the current view, then every change; returns the unsubscribe. Views are unchecked wire data. */
      subscribe: (onView: (view: unknown) => void) => () => void;
      act: (request: Record<string, unknown>) => Promise<unknown>;
      report: (report: Record<string, unknown>) => void;
    };
  };
}
