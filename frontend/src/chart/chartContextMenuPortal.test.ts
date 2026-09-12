/**
 * @vitest-environment jsdom
 */
import { afterEach, describe, expect, it } from 'vitest';
import { chartContextMenuPortalTarget } from './chartContextMenuPortal';

function setFullscreenElement(el: Element | null): void {
  Object.defineProperty(document, 'fullscreenElement', {
    configurable: true,
    value: el,
  });
}

describe('chartContextMenuPortalTarget', () => {
  afterEach(() => {
    setFullscreenElement(null);
    document.body.innerHTML = '';
  });

  it('portals to <body> when nothing is fullscreen', () => {
    const container = document.createElement('div');
    document.body.appendChild(container);
    expect(chartContextMenuPortalTarget(container)).toBe(document.body);
  });

  it('portals inside the fullscreen chart host so the menu still paints (#117)', () => {
    const host = document.createElement('div');
    const container = document.createElement('div');
    host.appendChild(container);
    document.body.appendChild(host);
    setFullscreenElement(host);
    expect(chartContextMenuPortalTarget(container)).toBe(host);
  });

  it('stays on <body> when another pane is the fullscreen element', () => {
    const otherPane = document.createElement('div');
    const container = document.createElement('div');
    document.body.append(otherPane, container);
    setFullscreenElement(otherPane);
    expect(chartContextMenuPortalTarget(container)).toBe(document.body);
  });
});
