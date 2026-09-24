/**
 * @vitest-environment jsdom
 */
import { afterEach, describe, expect, it } from 'vitest';
import { FIND_BAR_ATTR, findMatches, findPattern } from './findText';

function page(html: string): HTMLElement {
  const root = document.createElement('div');
  root.innerHTML = html;
  document.body.appendChild(root);
  return root;
}

const texts = (root: Element, query: string, limit = 100) =>
  findMatches(root, query, limit).matches.map((m) => m.range.toString());

afterEach(() => {
  document.body.innerHTML = '';
});

describe('findPattern', () => {
  it('ignores case, reads any spacing as one space, and treats the query as text', () => {
    const pattern = findPattern('  bull   FLAG ')!;
    expect('Bull flag'.match(pattern)?.[0]).toBe('Bull flag');
    expect('bull \n flag'.match(pattern)?.[0]).toBe('bull \n flag');
    expect(findPattern('$4.13 (x)')!.test('at $4.13 (x) now')).toBe(true);
    expect(findPattern('4.13')!.test('4913')).toBe(false);
    expect(findPattern('   ')).toBeNull();
  });
});

describe('findMatches', () => {
  it('finds text React split into several nodes, but never runs one cell into the next', () => {
    const root = page('<table><tr><td>GC</td><td>TK</td></tr></table><p></p>');
    const p = root.querySelector('p')!;
    for (const part of ['3', ' of ', '12']) p.appendChild(document.createTextNode(part));
    expect(texts(root, '3 of 12')).toEqual(['3 of 12']);
    expect(texts(root, 'GCTK')).toEqual([]);
    expect(texts(root, 'tk')).toEqual(['TK']);
  });

  it('marks a match that spans inline elements with one range', () => {
    const root = page('<div>Backend <b>v1007</b> answers</div>');
    const [match] = findMatches(root, 'backend v1007', 10).matches;
    expect(match.range.toString()).toBe('Backend v1007');
    expect(match.node.data).toBe('Backend ');
    expect(match.offset).toBe(0);
  });

  it('leaves out what is not shown: hidden panels, tooltips, list boxes, scripts and the find bar', () => {
    const root = page(`
      <div>GCTK on the board</div>
      <div hidden>GCTK in a closed tab</div>
      <div role="tooltip">GCTK in a tip</div>
      <select><option>GCTK</option></select>
      <script>var s = "GCTK";</script>
      <div ${FIND_BAR_ATTR}><span>GCTK typed in the find bar</span></div>`);
    expect(texts(root, 'gctk')).toEqual(['GCTK']);
    expect(findMatches(root, 'gctk', 10).matches[0].node.data).toBe('GCTK on the board');
  });

  it('stops at the limit and says there were more', () => {
    const root = page('<ul>' + '<li>AAPL</li>'.repeat(5) + '</ul>');
    const result = findMatches(root, 'aapl', 3);
    expect(result.matches).toHaveLength(3);
    expect(result.capped).toBe(true);
    expect(findMatches(root, 'aapl', 5).capped).toBe(false);
  });

  it('finds nothing for an empty query or an empty page', () => {
    expect(findMatches(page('<div>text</div>'), ' ', 10)).toEqual({ matches: [], capped: false });
    expect(findMatches(page(''), 'text', 10)).toEqual({ matches: [], capped: false });
  });
});
