import { useSyncExternalStore } from 'react';
import {
  getBrowserTimingSamples,
  subscribeBrowserTiming,
} from './browserTiming';
import type { BrowserTimingSample } from './types';

let cached: readonly BrowserTimingSample[] = [];
let cachedLength = -1;

function snapshot(): readonly BrowserTimingSample[] {
  const current = getBrowserTimingSamples();
  if (current.length !== cachedLength || current[0] !== cached[0]) {
    cached = [...current];
    cachedLength = current.length;
  }
  return cached;
}

export function useBrowserTimingSamples(): readonly BrowserTimingSample[] {
  return useSyncExternalStore(subscribeBrowserTiming, snapshot, snapshot);
}
