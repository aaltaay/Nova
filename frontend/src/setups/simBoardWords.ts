/**
 * What the Setups board is on the Sim desk off the live edge (ADR 029; operator ask
 * 2026-09-24): a Session Record re-read by today's templates (`replay.kind` `capture`),
 * or what Nova's live eyes recorded at the playhead (`journal`, backend
 * `eyes/playback.py`) -- every setup card as it stood then. The Setups panel and the
 * Bots page say it in the same words. Pure.
 */
import type { SetupsBoard, SetupSummary } from './types';

/** "08:07:02": a playhead to the second, Eastern. */
export function etHms(ts: number | null | undefined): string {
  if (!ts || !Number.isFinite(ts)) return '';
  return new Date(ts * 1000).toLocaleTimeString('en-US', { timeZone: 'America/New_York', hour12: false });
}

/** The board shows what the live eyes recorded, not the market now. */
export function isRecordedBoard(board: SetupsBoard | null | undefined): boolean {
  return board?.source === 'sim' && board.replay?.kind === 'journal';
}

/** One line: what the Sim board is following, and any stated absence. */
export function simBoardLine(board: SetupsBoard, summary: SetupSummary | null = null): string {
  const r = board.replay;
  if (r?.kind === 'journal') {
    const when = r.at ? `${etHms(r.at)} ET` : 'the playhead';
    const head = `Recorded · what Nova's eyes saw live at ${when}${r.date ? ` on ${r.date}` : ''}`;
    if (r.error) return `${head} · ${r.error}`;
    return r.note ? `${head} · ${r.note}` : head;
  }
  const what = `Sim eyes on ${r?.symbol ?? 'the replay'}${r?.date ? ` ${r.date}` : ''}`;
  if (r?.note) return `${what} · ${r.note}`;
  if (r?.error) return `${what} · the recording could not be read: ${r.error}`;
  if (r?.loading) return `${what} · reading the recording…`;
  return `${what} · following the playhead${summary?.template ? ` · template ${summary.template.name}` : ''}`;
}

/** The hover behind that line. */
export function simBoardTip(board: SetupsBoard): string {
  if (board.replay?.kind === 'journal') {
    return 'The Sim desk is off the live edge, so every setup card shows what Nova\'s live eyes recorded at the playhead: '
      + 'the rows, today\'s funnel up to that moment, and any proposal open then, which pops up as the playhead plays across it. '
      + 'Nothing is recomputed with today\'s rules, and nothing after the playhead is read.\n'
      + 'Off / Eyes, the template and its parameters are still today\'s controls.\n'
      + 'Load that day\'s Session Record instead to re-read the recording with today\'s templates.';
  }
  return 'The Sim eyes run today\'s templates over the loaded Session Record, following the playhead. '
    + 'Their proposals are practice proposals on this desk; nothing proposes live from a replay.';
}

/** A card with nothing to show at a recorded moment says which moment. */
export function recordedEmptyText(board: SetupsBoard | null | undefined): string | null {
  if (!isRecordedBoard(board)) return null;
  const at = etHms(board?.replay?.at);
  return at ? `Nothing forming at ${at} ET.` : 'Nothing forming at the playhead.';
}
