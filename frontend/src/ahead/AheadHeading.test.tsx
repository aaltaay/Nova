/**
 * @vitest-environment jsdom
 *
 * The words over Ahead's zone (ADR 061): they follow the zone, and some always show while Ahead is on.
 */
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

  it('puts the legend at the bottom left only when the zone leaves it room', () => {
    const { ref } = mount(sampleScene());
    const legend = screen.getByTestId('ahead-legend');
    act(() => ref.current?.place({ left: 400, right: 700, top: 0 }, 26));
    expect(legend.style.display).toBe('');
    expect(legend.style.bottom).toBe('30px');
    expect(legend.style.maxWidth).toBe('380px');
    act(() => ref.current?.place({ left: 150, right: 450, top: 0 }, 26));
    expect(legend.style.display).toBe('none');
  });

  it('opens the Ahead panel from the ▸', () => {
    mount();
    fireEvent.click(screen.getByTestId('ahead-open-sheet-note'));
    expect(aheadSheetOpen('XYZ')).toBe(true);
  });
});
