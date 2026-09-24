/**
 * Every setup's parameters and templates for the Bots page (ADR 029): read on
 * mount and every `BOTS_TEMPLATES_POLL_MS` (each setup's template
 * read-out moves as setups trigger), and replaced setup by setup from each
 * write's own answer.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { BOTS_TEMPLATES_POLL_MS } from '../constantGroups/bots_page';
import { fetchTemplates } from './templatesApi';
import type { SetupTemplates, TemplatesPayload } from './templateTypes';

export type SetupTemplatesState = ReturnType<typeof useSetupTemplates>;

export function useSetupTemplates(enabled = true) {
  const [payload, setPayload] = useState<TemplatesPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const alive = useRef(true);

  const refresh = useCallback(async () => {
    try {
      const next = await fetchTemplates();
      if (!alive.current) return;
      setPayload(next);
      setError(null);
    } catch (err) {
      if (!alive.current) return;
      setError(err instanceof Error ? err.message : String(err));
    }
  }, []);

  useEffect(() => {
    alive.current = true;
    if (!enabled) return () => { alive.current = false; };
    void refresh();
    const timer = window.setInterval(() => void refresh(), BOTS_TEMPLATES_POLL_MS);
    return () => {
      alive.current = false;
      window.clearInterval(timer);
    };
  }, [enabled, refresh]);

  /** Put a write's answer in place of its setup. */
  const apply = useCallback((setup: SetupTemplates) => {
    setPayload(prev => (prev ? { ...prev, setups: prev.setups.map(s => (s.id === setup.id ? setup : s)) } : prev));
  }, []);

  const setup = useCallback((id: string) => payload?.setups.find(s => s.id === id) ?? null, [payload]);

  return { payload, error, refresh, apply, setup };
}
