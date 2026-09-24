import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const here = dirname(fileURLToPath(import.meta.url));
const app = readFileSync(resolve(here, './App.tsx'), 'utf8').replace(/\r\n/g, '\n');
const dockCss = readFileSync(resolve(here, './hod_momo/hodMomoDock.css'), 'utf8').replace(/\r\n/g, '\n');

describe('App branch layout (QA R39)', () => {
  it('keeps TraderDockLayer out of an error boundary inside .nova-app-branch', () => {
    // An AppErrorBoundary renders an .app-shell-host div, and
    // `.nova-app-branch > .app-shell-host` takes a flex share of the branch:
    // wrapping the (empty) dock layer blanked the top half of the Trader.
    expect(dockCss).toMatch(/\.nova-app-branch > \.app-shell-host/);
    expect(app).not.toMatch(/<AppErrorBoundary[^>]*>\s*<TraderDockLayer/);
    expect(app).toMatch(/<TraderDockLayer \/>/);
  });

  it('gives a pop-out its own symbol menu host -- it has no app bar to carry one', () => {
    // A pop-out's Trader tab strip and Focus rail open the right-click symbol
    // menu; with no host the right-click ate the browser menu and showed nothing.
    expect(app).toMatch(/\{!detached && <GlobalAppBar \/>\}/);
    expect(app).toMatch(/\{detached && <BotSymbolMenuHost \/>\}/);
  });
});
