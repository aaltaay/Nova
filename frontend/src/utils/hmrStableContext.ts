/**
 * `createContext(null)` that keeps one identity across Vite HMR updates of the
 * module that owns it.
 *
 * A context module that also exports hooks is not a Fast Refresh boundary, so
 * an edit to it -- or to a hook it imports -- re-runs it and would mint a
 * second context. When the same update also refreshes a component, React
 * re-renders the mounted Provider from the new module while its consumers
 * still read the old context, and their "must be used within" hook throws
 * (the desk showed "useLiveScannerFeed must be used within
 * ScannerDataProvider" after a pull into the running dev server). Keeping the
 * context in `import.meta.hot.data` gives every generation of the module the
 * same object. Production builds have no `import.meta.hot`; Vitest's has no
 * `data`. Either way this is a plain `createContext(null)`.
 */
import { createContext, type Context } from 'react';

/** The part of `import.meta.hot` this needs; the data survives module re-runs. */
export type HmrData = { readonly data?: Record<string, unknown> };

export function hmrStableContext<T>(hot: HmrData | undefined, name: string): Context<T | null> {
  const data = hot?.data;
  const kept = data?.[name] as Context<T | null> | undefined;
  if (kept) return kept;
  const context = createContext<T | null>(null);
  if (data) data[name] = context;
  return context;
}
