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
    /** Electron IPC: open an allowlisted HTTPS URL in the system browser. */
    openExternal?: (url: string) => Promise<boolean>;
    /** Electron IPC: stop + start the local FastAPI sidecar, then wait for health. */
    /** `from` / `to`: the backend's revision before and after (null when it does not say). */
    restartApi?: () => Promise<{ ok: boolean; error?: string; from?: string | null; to?: string | null }>;
    /** Electron IPC: the update notice and What's new card (desktop_update/). */
    updates?: {
      /** Called with the current view, then every change; returns the unsubscribe. Views are unchecked wire data. */
      subscribe: (onView: (view: unknown) => void) => () => void;
      act: (request: { action: string; url?: string }) => Promise<{ ok: boolean; error?: string }>;
    };
  };
}
