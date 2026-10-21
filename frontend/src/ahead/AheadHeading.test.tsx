/**
 * @vitest-environment jsdom
 *
 * The words over Ahead's zone (ADR 065): they follow the zone, and some always show while Ahead is on.
 */
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { createRef } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { AheadHeading, type HeadingHandle } from './AheadHeading';
import { aheadSheetOpen, resetAheadStoreForTesting } from './aheadStore';
import { sampleScene } from './aheadTestKit';

afterEach(() => {
  cleanup();
  act(() => resetAheadStoreForTesting());
});

function mount(scene = sampleScene({ words: ['AI view hidden: not passed.'] })) {
  const ref = createRef<HeadingHandle>();
  const onSize = vi.fn();
  render(<AheadHeading ref={ref} symbol="XYZ" scene={scene} onSize={onSize} />);
  return { ref, onSize };
}

describe('AheadHeading', () => {
  it('sits on the zone when it fits, the sentence at the top right when it does not', () => {
    const { ref } = mount();
    const heading = screen.getByTestId('ahead-heading');
    const note = screen.getByTestId('ahead-pane-note');
    expect(note.style.display).toBe('');
    act(() => ref.current?.place({ left: 400, right: 700, top: 0 }, 26));
    expect(heading.style.display).toBe('');
    expect(heading.style.transform).toBe('translate(410px, 6px)');
    expect(note.style.display).toBe('none');
    expect(heading.textContent).toContain('AHEAD · next 15 min');
    expect(heading.textContent).toContain('AI view, not data');
    expect(heading.textContent).toContain('AI view hidden: not passed.');
    act(() => ref.current?.place({ left: 600, right: 700, top: 0 }, 26));
    expect(heading.style.display).toBe('none');
    expect(note.style.display).toBe('');
    act(() => ref.current?.place(null, 26));
    expect(note.textContent).toContain('AI view hidden: not passed.');
  });

  it('lays no legend over the candles or the volume (the Ahead panel holds it), the tags on one row', () => {
    const { ref } = mount(sampleScene({ zone: { title: 'AHEAD · next 15 min', nowText: 'now 09:10', tags: [
      { text: 'AI view, not data', fg: '#fff', bg: '#000' }, { text: 'no exam yet', fg: '#fff', bg: '#000' }] } }));
    act(() => ref.current?.place({ left: 400, right: 700, top: 0 }, 26));
    expect(screen.queryByTestId('ahead-legend')).toBeNull();
    expect(screen.getByTestId('ahead-tags').children).toHaveLength(2);
  });

  it('puts "now" just left of the zone in the DOM, on a backdrop, and reports both rectangles', () => {
    const { ref, onSize } = mount();
    const now = screen.getByTestId('ahead-now');
    expect(now.className).toBe('ahead-now');
    expect(now.textContent).toBe('now 09:10');
    act(() => ref.current?.place({ left: 400, right: 700, top: 0 }, 26));
    expect(now.style.display).toBe('');
    // jsdom measures nothing: the chip's right edge sits 4 px left of the zone.
    expect(now.style.transform).toBe('translate(396px, 6px)');
    expect(onSize).toHaveBeenLastCalledWith([]);
    act(() => ref.current?.place(null, 26));
    expect(now.style.display).toBe('none');
  });

  it("ends short of the stock read's words over the zone's top, and gives way when that leaves too little room", () => {
    const { ref } = mount();
    const heading = screen.getByTestId('ahead-heading');
    act(() => ref.current?.place({ left: 400, right: 700, top: 0, capRight: 600 }, 26));
    expect(heading.style.maxWidth).toBe('184px');
    act(() => ref.current?.place({ left: 400, right: 700, top: 0, capRight: 520 }, 26));
    expect(heading.style.display).toBe('none');
    expect(screen.getByTestId('ahead-pane-note').style.display).toBe('');
  });

  it('counts its padding inside that room, so the painted backdrop ends short of those words too', () => {
    // The app has no global border-box reset: without it the 6 px padding each side would paint past capRight.
    const css = readFileSync(resolve(dirname(fileURLToPath(import.meta.url)), './ahead.css'), 'utf8');
    for (const cls of ['.ahead-heading', '.ahead-now']) {
      const rule = css.slice(css.indexOf(`${cls} {`), css.indexOf('}', css.indexOf(`${cls} {`)));
      expect(rule).toMatch(/box-sizing:\s*border-box/);
    }
  });

  it('opens the Ahead panel from the ▸', () => {
    mount();
    fireEvent.click(screen.getByTestId('ahead-open-sheet-note'));
    expect(aheadSheetOpen('XYZ')).toBe(true);
  });
});
