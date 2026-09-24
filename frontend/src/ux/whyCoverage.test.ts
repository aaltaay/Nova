/**
 * Every locked control says why (operator report 2026-09-23: "these are always
 * unclickable, at least it should explain why ... gaps may exist everywhere").
 *
 * Parses every component under src/ and fails on a JSX element that can be
 * disabled without carrying its reason:
 *
 * - a DOM element (or a wrapper that passes its props to one) with `disabled`
 *   or `aria-disabled` needs `data-why` (`ux/whyTip.ts` shows it on hover and on
 *   a refused press) -- `{...whyProps(locked, reason)}` counts;
 * - any other component given `disabled` needs `why`, the reason it forwards to
 *   its own control (whose leaf this test checks in turn).
 *
 * `<option>` is exempt: a native select's list is drawn outside the page, so a
 * disabled option says why in its own label instead.
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import ts from 'typescript';
import { describe, expect, it } from 'vitest';

const SRC = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
/** Components that pass their props straight to a DOM control. */
const DOM_WRAPPERS = new Set(['Button', 'AlertDialogAction', 'AlertDialogCancel', 'InputOTP']);
const EXEMPT_TAGS = new Set(['option']);

interface Finding {
  where: string;
  tag: string;
  attr: string;
  needs: string;
}

function componentFiles(dir: string, out: string[] = []): string[] {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) componentFiles(full, out);
    else if (entry.name.endsWith('.tsx') && !entry.name.endsWith('.test.tsx')) out.push(full);
  }
  return out;
}

function attrNamed(attrs: ts.JsxAttributes, name: string): ts.JsxAttribute | undefined {
  return attrs.properties.find(
    (a): a is ts.JsxAttribute => ts.isJsxAttribute(a) && a.name.getText() === name,
  );
}

function isLiteralFalse(attr: ts.JsxAttribute): boolean {
  const init = attr.initializer;
  if (!init) return false;
  if (ts.isStringLiteral(init)) return init.text === 'false';
  return ts.isJsxExpression(init) && init.expression?.kind === ts.SyntaxKind.FalseKeyword;
}

function spreadsWhy(attrs: ts.JsxAttributes): boolean {
  return attrs.properties.some(a => ts.isJsxSpreadAttribute(a) && /\bwhyProps\(/.test(a.expression.getText()));
}

function findUnexplained(files: string[]): Finding[] {
  const found: Finding[] = [];
  for (const file of files) {
    const text = fs.readFileSync(file, 'utf8');
    const sf = ts.createSourceFile(file, text, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
    const visit = (node: ts.Node) => {
      if (ts.isJsxOpeningElement(node) || ts.isJsxSelfClosingElement(node)) {
        const tag = node.tagName.getText(sf);
        const lock = [attrNamed(node.attributes, 'disabled'), attrNamed(node.attributes, 'aria-disabled')]
          .find(a => a && !isLiteralFalse(a));
        if (lock && !EXEMPT_TAGS.has(tag)) {
          const dom = /^[a-z]/.test(tag) || DOM_WRAPPERS.has(tag);
          const has = spreadsWhy(node.attributes)
            || Boolean(attrNamed(node.attributes, 'data-why'))
            || (!dom && Boolean(attrNamed(node.attributes, 'why')));
          if (!has) {
            const line = sf.getLineAndCharacterOfPosition(node.getStart(sf)).line + 1;
            found.push({
              where: `${path.relative(SRC, file).replace(/\\/g, '/')}:${line}`,
              tag,
              attr: lock.name.getText(sf),
              needs: dom ? 'data-why' : 'why',
            });
          }
        }
      }
      ts.forEachChild(node, visit);
    };
    visit(sf);
  }
  return found;
}

describe('every locked control says why', () => {
  it('no JSX element can be disabled without its reason', () => {
    const missing = findUnexplained(componentFiles(SRC));
    const report = missing.map(f => `  ${f.where} <${f.tag} ${f.attr}> needs ${f.needs}`).join('\n');
    expect(missing, `Locked controls with no reason (see ux/whyTip.ts):\n${report}`).toEqual([]);
  });

  it('the parser sees a bare disabled button, and accepts data-why / why / whyProps', () => {
    const tmp = path.join(os.tmpdir(), `why-coverage-probe-${process.pid}.tsx`);
    fs.writeFileSync(tmp, [
      'export const A = () => <button disabled={x}>a</button>;',
      'export const B = () => <button disabled={x} data-why={r}>b</button>;',
      'export const C = () => <Thing disabled={x} why={r} />;',
      'export const D = () => <Thing disabled={x} />;',
      'export const E = () => <input disabled {...whyProps(x, r)} />;',
      'export const F = () => <button disabled={false}>f</button>;',
      'export const G = () => <option disabled>g</option>;',
      'export const H = () => <div aria-disabled="true">h</div>;',
    ].join('\n'));
    try {
      const found = findUnexplained([tmp]).map(f => `${f.where.split(':').pop()} ${f.tag} ${f.needs}`);
      expect(found).toEqual(['1 button data-why', '4 Thing why', '8 div data-why']);
    } finally {
      fs.rmSync(tmp, { force: true });
    }
  });
});
