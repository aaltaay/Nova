/** @vitest-environment jsdom */
import { describe, expect, it } from 'vitest';
import { measureChartFillHeight } from './measureChartFillHeight';
import { CHART_HEIGHT_PANEL, CHART_PANEL_SLOT_MAX_PX } from '../constants';

describe('measureChartFillHeight', () => {
  it('returns card leftover after chrome siblings', () => {
    const card = document.createElement('div');
    card.className = 'chart-card';
    Object.defineProperty(card, 'clientHeight', { value: 400 });
    const header = document.createElement('div');
    Object.defineProperty(header, 'offsetHeight', { value: 48 });
    const toolbar = document.createElement('div');
    Object.defineProperty(toolbar, 'offsetHeight', { value: 32 });
    const body = document.createElement('div');
    Object.defineProperty(body, 'clientHeight', { value: 0 });
    card.append(header, toolbar, body);

    expect(measureChartFillHeight(body, CHART_HEIGHT_PANEL)).toBe(320);
  });

  it('falls back when card has no height yet', () => {
    const body = document.createElement('div');
    Object.defineProperty(body, 'clientHeight', { value: 0 });
    expect(measureChartFillHeight(body, CHART_HEIGHT_PANEL)).toBe(CHART_HEIGHT_PANEL);
  });
});

describe('CHART_PANEL_SLOT_MAX_PX', () => {
  it('fits panel body plus chrome so CSS max-height cannot clip the time axis', () => {
    expect(CHART_PANEL_SLOT_MAX_PX).toBeGreaterThanOrEqual(CHART_HEIGHT_PANEL + 100);
    expect(CHART_PANEL_SLOT_MAX_PX).toBe(400);
  });
});
