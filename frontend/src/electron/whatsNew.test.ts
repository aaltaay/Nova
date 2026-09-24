/**
 * What's new opens on the first launch of a new version, lists what the update
 * brought, and stays closed once the operator closes it.
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { WHATS_NEW_FILE, createWhatsNew } from '../../electron/whatsNew.mjs';

type Card = null | { mode: string; tag: string; since: string | null; notes: { loading: boolean; releases: unknown[] } };

let dir = '';

function setup({ installed = 'v980', listening = true } = {}) {
  let view: { whats_new: Card } = { whats_new: null };
  const bridge = {
    set: vi.fn((part: string, value: Card) => {
      view = { ...view, [part]: value };
    }),
    view: () => view,
    hasListener: () => listening,
  };
  const notes = { loading: false, error: null, releases: [{ tag: installed }], more: 0 };
  const notesSource = { load: vi.fn(async () => notes) };
  const showDialog = vi.fn(async () => ({ response: 0 }));
  const logger = { info: vi.fn(), warn: vi.fn() };
  const whatsNew = createWhatsNew({ bridge, notesSource, dir: () => dir, installedTag: installed, logger, showDialog });
  return { whatsNew, bridge, notesSource, showDialog, logger, card: () => view.whats_new };
}

const seenFile = () => path.join(dir, WHATS_NEW_FILE);
const writeSeen = (body: unknown) => fs.writeFileSync(seenFile(), JSON.stringify(body));

beforeEach(() => {
  dir = fs.mkdtempSync(path.join(os.tmpdir(), 'nova-whats-new-'));
});

afterEach(() => {
  fs.rmSync(dir, { recursive: true, force: true });
});

describe("What's new", () => {
  it('lists every release since the last one read, loading first', async () => {
    writeSeen({ schema_version: 1, seen_tag: 'v975' });
    const { whatsNew, bridge, notesSource, card } = setup();
    await whatsNew.start();
    expect(notesSource.load).toHaveBeenCalledWith({ after: 'v975', through: 'v980', since: 'v975' });
    expect(bridge.set.mock.calls[0][1]).toMatchObject({ mode: 'updated', since: 'v975', notes: { loading: true } });
    expect(card()).toMatchObject({ mode: 'updated', tag: 'v980', since: 'v975', notes: { loading: false } });
  });

  it("shows the installed release's own notes when nothing was read before", async () => {
    const { whatsNew, notesSource, card } = setup();
    await whatsNew.start();
    expect(notesSource.load).toHaveBeenCalledWith({ after: 'v979', through: 'v980', since: null });
    expect(card()?.since).toBeNull();
  });

  it('records the version as read on close, and stays closed on the next launch', async () => {
    const first = setup();
    await first.whatsNew.start();
    first.whatsNew.close();
    expect(first.card()).toBeNull();
    expect(JSON.parse(fs.readFileSync(seenFile(), 'utf8'))).toMatchObject({ schema_version: 1, seen_tag: 'v980' });
    const next = setup();
    await next.whatsNew.start();
    expect(next.notesSource.load).not.toHaveBeenCalled();
    expect(next.card()).toBeNull();
  });

  it('stays closed when closed while its notes were loading', async () => {
    const { whatsNew, notesSource, card } = setup();
    let release: (value: unknown) => void = () => {};
    notesSource.load.mockReturnValueOnce(new Promise((resolve) => (release = resolve)) as never);
    const started = whatsNew.start();
    whatsNew.close();
    release({ loading: false, releases: [] });
    await started;
    expect(card()).toBeNull();
  });

  it('leaves a file of another schema version alone and shows nothing', async () => {
    writeSeen({ schema_version: 2, seen_tag: 'v1200' });
    const { whatsNew, notesSource, logger } = setup();
    await whatsNew.start();
    expect(notesSource.load).not.toHaveBeenCalled();
    expect(logger.warn).toHaveBeenCalledWith(expect.stringContaining('schema_version 2'));
    expect(JSON.parse(fs.readFileSync(seenFile(), 'utf8')).schema_version).toBe(2);
  });

  it('Help > What\'s New opens the recent releases on the desk, or in a dialog when the window cannot', async () => {
    const onDesk = setup();
    await onDesk.whatsNew.openRecent();
    expect(onDesk.card()?.mode).toBe('recent');
    expect(onDesk.showDialog).not.toHaveBeenCalled();
    const noWindow = setup({ listening: false });
    await noWindow.whatsNew.openRecent();
    expect(noWindow.showDialog).toHaveBeenCalledWith(expect.objectContaining({ title: "What's new in Nova v980" }));
  });
});
