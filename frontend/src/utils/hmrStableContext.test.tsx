import { useContext } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { hmrStableContext } from './hmrStableContext';

describe('hmrStableContext', () => {
  it('gives a re-run module the context its first run made', () => {
    const hot = { data: {} };
    const first = hmrStableContext<string>(hot, 'ScannerDataContext');
    const rerun = hmrStableContext<string>(hot, 'ScannerDataContext');
    expect(rerun).toBe(first);
  });

  it('lets a consumer from the old module read a Provider from the new one', () => {
    const hot = { data: {} };
    const oldModule = hmrStableContext<string>(hot, 'ScannerDataContext');
    const newModule = hmrStableContext<string>(hot, 'ScannerDataContext');
    function OldConsumer() {
      return <span>{useContext(oldModule) ?? 'missing provider'}</span>;
    }
    const html = renderToStaticMarkup(
      <newModule.Provider value="feed">
        <OldConsumer />
      </newModule.Provider>,
    );
    expect(html).toBe('<span>feed</span>');
  });

  it('keeps two contexts in one module apart', () => {
    const hot = { data: {} };
    expect(hmrStableContext(hot, 'A')).not.toBe(hmrStableContext(hot, 'B'));
  });

  it('treats a hot context without data (Vitest) as no HMR', () => {
    const a = hmrStableContext<number>({}, 'X');
    const b = hmrStableContext<number>({}, 'X');
    expect(a).not.toBe(b);
  });

  it('makes a plain null-default context without HMR (production)', () => {
    const a = hmrStableContext<number>(undefined, 'X');
    const b = hmrStableContext<number>(undefined, 'X');
    expect(a).not.toBe(b);
    function Reader() {
      return <span>{String(useContext(a))}</span>;
    }
    expect(renderToStaticMarkup(<Reader />)).toBe('<span>null</span>');
  });
});
