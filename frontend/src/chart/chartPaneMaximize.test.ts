/**
 * @vitest-environment jsdom
 */
import { describe, expect, it } from 'vitest';
import { shouldToggleChartPaneMaximize } from './chartPaneMaximize';

function eventOn(el: Element) {
  return { target: el };
}

describe('shouldToggleChartPaneMaximize', () => {
  it('allows a double-click on the pane body when no tool is armed', () => {
    const body = document.createElement('div');
    body.className = 'chart-body';
    expect(shouldToggleChartPaneMaximize(eventOn(body), null)).toBe(true);
  });

  it('refuses while a drawing tool is armed so place clicks stay place clicks', () => {
    const body = document.createElement('div');
    body.className = 'chart-body';
    expect(shouldToggleChartPaneMaximize(eventOn(body), 'TrendLine')).toBe(false);
    expect(shouldToggleChartPaneMaximize(eventOn(body), 'CrossLine')).toBe(false);
  });

  it('refuses header buttons and resize handles', () => {
    const cell = document.createElement('div');
    const button = document.createElement('button');
    button.setAttribute('aria-label', 'Maximize chart');
    const handle = document.createElement('div');
    handle.className = 'resize-handle';
    cell.append(button, handle);
    expect(shouldToggleChartPaneMaximize(eventOn(button), null)).toBe(false);
    expect(shouldToggleChartPaneMaximize(eventOn(handle), null)).toBe(false);
  });
});
