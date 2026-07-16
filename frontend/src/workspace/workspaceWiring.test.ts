import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const here = dirname(fileURLToPath(import.meta.url));
const src = join(here, '..');

describe('WorkspaceContext wiring (Phase 2)', () => {
  it('App mounts WorkspaceProvider and Dashboard takes no selection props', () => {
    const app = readFileSync(join(src, 'App.tsx'), 'utf8');
    const dash = readFileSync(join(src, 'pages/DashboardPage.tsx'), 'utf8');
    expect(app).toMatch(/WorkspaceProvider/);
    expect(app).toMatch(/ModuleVisibilityProvider/);
    expect(app).toMatch(/LayoutStoreProvider/);
    expect(app).toMatch(/<DashboardPage\s*\/>/);
    expect(dash).toMatch(/useWorkspace\(/);
    expect(dash).not.toMatch(/interface Props/);
  });

  it('StockViewPage does not fetch /api/config independently', () => {
    const page = readFileSync(join(src, 'pages/StockViewPage.tsx'), 'utf8');
    expect(page).toMatch(/useWorkspace\(/);
    expect(page).not.toMatch(/\/config/);
    expect(page).not.toMatch(/setDiscoveryProvider/);
  });

  it('SidePanel and TickerDetailContent read workspace instead of drilled discovery props', () => {
    const side = readFileSync(join(src, 'components/SidePanel.tsx'), 'utf8');
    const detail = readFileSync(join(src, 'components/TickerDetailContent.tsx'), 'utf8');
    expect(side).toMatch(/useWorkspace\(/);
    expect(side).not.toMatch(/discoveryProvider\?:/);
    expect(side).not.toMatch(/alpacaFeed\?:/);
    expect(detail).toMatch(/useWorkspace\(/);
    expect(detail).not.toMatch(/ibkrConnected\?:/);
    expect(detail).not.toMatch(/discoveryProvider\?:/);
  });

  it('Phase 3 quote panels read workspace (DataSources / QuoteHeader / DepthTape)', () => {
    const data = readFileSync(join(src, 'modules/DataSourcesPanel.tsx'), 'utf8');
    const quote = readFileSync(join(src, 'modules/QuoteHeaderPanel.tsx'), 'utf8');
    const depth = readFileSync(join(src, 'modules/DepthTapePanel.tsx'), 'utf8');
    expect(data).toMatch(/useWorkspace\(/);
    expect(quote).toMatch(/useWorkspace\(/);
    expect(depth).toMatch(/useWorkspace\(/);
  });
});
