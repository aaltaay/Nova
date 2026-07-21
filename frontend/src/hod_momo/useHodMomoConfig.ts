import { useCallback, useEffect, useReducer, useRef } from 'react';
import { novaFetch } from '../api/novaFetch';
import { API_BASE_URL } from '../constants';
import type {
  HodMomoConfigAction,
  HodMomoConfigState,
  MasterGateConfig,
  StrategyConfig,
} from './types';

const API = `${API_BASE_URL}/api`;

function reducer(state: HodMomoConfigState, action: HodMomoConfigAction): HodMomoConfigState {
  switch (action.type) {
    case 'LOADED':
      return { ...state, ...action.payload, loaded: true };
    case 'UPDATE_STRATEGY': {
      const sid = String(action.strategyId);
      const existing = state.strategies[sid];
      if (!existing) return state;
      return {
        ...state,
        strategies: {
          ...state.strategies,
          [sid]: { ...existing, ...action.patch },
        },
      };
    }
    case 'UPDATE_MASTER':
      return { ...state, master: { ...state.master, ...action.patch } };
    case 'RESET_STRATEGY': {
      const sid = String(action.strategyId);
      return {
        ...state,
        strategies: { ...state.strategies, [sid]: action.defaults },
      };
    }
    case 'RESET_ALL':
      return { ...state, ...action.payload, loaded: true };
    default:
      return state;
  }
}

const INITIAL_STATE: HodMomoConfigState = {
  master: {
    hod_required: true,
    surge_pct: 3.0,
    surge_window_min: 5,
    min_rvol: 2.0,
    premarket_min_rvol: 1.0,
    afterhours_min_rvol: 1.0,
    cooldown_sec: 60.0,
    consolidation_sec: 5.0,
  },
  strategies: {},
  loaded: false,
};

export interface UseHodMomoConfigReturn {
  state: HodMomoConfigState;
  updateStrategy: (strategyId: number, patch: Partial<StrategyConfig>) => void;
  updateMaster: (patch: Partial<MasterGateConfig>) => void;
  resetStrategy: (strategyId: number) => Promise<void>;
  resetAll: () => Promise<void>;
}

export function useHodMomoConfig(): UseHodMomoConfigReturn {
  const [state, dispatch] = useReducer(reducer, INITIAL_STATE);
  const debounceRef = useRef<Record<string, ReturnType<typeof setTimeout>>>({});

  // Load configs on mount
  useEffect(() => {
    fetch(`${API}/hod-momo/config`)
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (data?.strategies && data?.master) {
          dispatch({
            type: 'LOADED',
            payload: { master: data.master as MasterGateConfig, strategies: data.strategies },
          });
        }
      })
      .catch((err) => {
        console.error('[Nova] HOD Momo config load failed', err);
      });
  }, []);

  // Debounced POST helper (300ms) to avoid hammering the backend on every keystroke
  const debouncedPost = useCallback((key: string, body: object) => {
    if (debounceRef.current[key]) clearTimeout(debounceRef.current[key]);
    debounceRef.current[key] = setTimeout(() => {
      novaFetch(`${API}/hod-momo/config`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      }).catch((err) => {
        console.error('[Nova] HOD Momo config save failed', err);
      });
    }, 300);
  }, []);

  const updateStrategy = useCallback((strategyId: number, patch: Partial<StrategyConfig>) => {
    dispatch({ type: 'UPDATE_STRATEGY', strategyId, patch });
    debouncedPost(`strategy-${strategyId}`, { scope: 'strategy', strategy_id: strategyId, patch });
  }, [debouncedPost]);

  const updateMaster = useCallback((patch: Partial<MasterGateConfig>) => {
    dispatch({ type: 'UPDATE_MASTER', patch });
    debouncedPost('master', { scope: 'master', patch });
  }, [debouncedPost]);

  const resetStrategy = useCallback(async (strategyId: number) => {
    const res = await novaFetch(`${API}/hod-momo/config`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ scope: 'reset_one', strategy_id: strategyId }),
    });
    if (res.ok) {
      const defaults = await res.json() as StrategyConfig;
      dispatch({ type: 'RESET_STRATEGY', strategyId, defaults });
    }
  }, []);

  const resetAll = useCallback(async () => {
    const res = await novaFetch(`${API}/hod-momo/config`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ scope: 'reset_all' }),
    });
    if (res.ok) {
      const data = await res.json();
      if (data?.strategies && data?.master) {
        dispatch({ type: 'RESET_ALL', payload: { master: data.master, strategies: data.strategies } });
      }
    }
  }, []);

  return { state, updateStrategy, updateMaster, resetStrategy, resetAll };
}
