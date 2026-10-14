/**
 * The strategies' buckets (ADR 049, #778 step 5): each sits where its own switch puts it, a short at On whose test
 * has not passed is held at Eyes and says so, and each row says how far its evidence has come.
 */
import { describe, expect, it } from 'vitest';
import { bucketOf, bucketsOf, statusOf, type BucketRow } from './strategyBuckets';

function row(partial: Partial<BucketRow> = {}): BucketRow {
  return { id: 'first_pullback', label: 'First pullback', side: 'long', own: 2, locked: null, test: null,
    readout: { state: 'collecting', passed: false, reason: '12 of 50 go so far', go_triggered: 12, min_go: 50,
      go_avg_net_r: 0.31 }, ...partial };
}

const queued = { state: 'queued', text: 'five-year test queued: run it on the desk', rules_hash: null, matches: null };
const passed = { state: 'passed', text: 'five-year test passed: 412 trades', rules_hash: 'abc', matches: true };

describe('strategyBuckets', () => {
  it('puts a strategy where its own switch is', () => {
    expect(bucketOf(row({ own: 2 }))).toBe(2);
    expect(bucketOf(row({ own: 1 }))).toBe(1);
    expect(bucketOf(row({ own: 0 }))).toBe(0);
  });

  it('keeps a short in its chosen bucket even with a legacy research lock', () => {
    const selected = row({ id: 'bear_flag', side: 'short', own: 2, test: queued,
      locked: 'On waits on the bear flag five-year test' });
    expect(bucketOf(selected)).toBe(2);
    expect(statusOf(selected)).toMatchObject({ text: 'Test queued', tone: 'muted' });
    expect(bucketOf({ ...selected, test: passed })).toBe(2);
    expect(statusOf({ ...selected, test: passed })).toMatchObject({ text: 'Test passed', tone: 'ok' });
  });

  it('says a long\'s read-out, and tells a read-out loading from one not reported', () => {
    expect(statusOf(row())).toMatchObject({ text: 'Read-out collecting · 12/50 go', tone: 'muted' });
    expect(statusOf(row()).tip).toMatch(/^12 of 50 go so far\n/);
    expect(statusOf(row({ readout: undefined })).text).toBe('Read-out loading');
    expect(statusOf(row({ readout: null })).text).toBe('No read-out reported');
    expect(statusOf(row({ side: 'short', test: null })).text).toBe('Test not reported');
  });

  it('keeps the playbook\'s order inside each bucket', () => {
    const rows = [row({ id: 'a', own: 0 }), row({ id: 'b', own: 2 }), row({ id: 'c', own: 0 }), row({ id: 'd', own: 1 })];
    const got = bucketsOf(rows);
    expect(got[2].map(r => r.id)).toEqual(['b']);
    expect(got[1].map(r => r.id)).toEqual(['d']);
    expect(got[0].map(r => r.id)).toEqual(['a', 'c']);
  });
});
