/**
 * React 19 checks globalThis.IS_REACT_ACT_ENVIRONMENT in isConcurrentActEnvironment().
 * Without this flag, every act()-wrapped createRoot render warns and React disables
 * the "update was not wrapped in act(...)" safety net.
 *
 * Wired via vite.config.ts test.setupFiles — not a product tunable.
 */
declare global {
  var IS_REACT_ACT_ENVIRONMENT: boolean | undefined
}

globalThis.IS_REACT_ACT_ENVIRONMENT = true

export {}
