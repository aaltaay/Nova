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
    restartApi?: () => Promise<{ ok: boolean; error?: string }>;
  };
}
