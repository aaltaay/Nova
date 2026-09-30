/** @vitest-environment jsdom */
import { act, render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { sameTopOfBook, TopOfBookProvider, useTopOfBook, type TopOfBook } from './TopOfBookContext';

const BOOK: TopOfBook = { symbol: 'CNTB', bid: 1.3, ask: 1.31, depthSubscribed: true };

describe('top of book', () => {
  it('compares what a reader can see', () => {
    expect(sameTopOfBook(BOOK, { ...BOOK })).toBe(true);
    expect(sameTopOfBook(BOOK, { ...BOOK, ask: 1.32 })).toBe(false);
    expect(sameTopOfBook(BOOK, { ...BOOK, depthSubscribed: false })).toBe(false);
    expect(sameTopOfBook(null, null)).toBe(true);
    expect(sameTopOfBook(BOOK, null)).toBe(false);
  });

  it('does not re-render its readers for a book with the same best bid and ask', () => {
    let renders = 0;
    let publish: (next: TopOfBook | null) => void = () => undefined;
    let seen: TopOfBook | null = null;
    function Reader() {
      const { topOfBook, setTopOfBook } = useTopOfBook();
      renders += 1;
      publish = setTopOfBook;
      seen = topOfBook;
      return null;
    }
    render(
      <TopOfBookProvider>
        <Reader />
      </TopOfBookProvider>,
    );
    act(() => publish(BOOK));
    const after = renders;
    const first = seen;
    act(() => publish({ ...BOOK }));
    act(() => publish({ ...BOOK }));
    expect(renders).toBe(after);
    expect(seen).toBe(first);
    act(() => publish({ ...BOOK, bid: 1.29 }));
    expect(renders).toBe(after + 1);
    expect(seen).toEqual({ ...BOOK, bid: 1.29 });
  });
});
