import { describe, expect, it, vi } from 'vitest';
import { buildProfile } from './volumeProfile';
import { fetchVolumeProfile, profileToWire, wireToAnswer } from './volumeProfileApi';

const novaFetch = vi.fn();
vi.mock('../api/novaFetch', () => ({ novaFetch: (...a: unknown[]) => novaFetch(...a) }));

const flat = (t: number, price: number, v: number) => ({ t, o: price, h: price, l: price, c: price, v });

describe('the volume-profile wire', () => {
  it('turns a profile into the backend shape and back', () => {
    const p = buildProfile([{ t: 0, o: 100, h: 101, l: 100, c: 101, v: 10 }, flat(60, 100.45, 50)], 0, 120, 10)!;
    const back = wireToAnswer(profileToWire('AAPL', 'today', p, 'bars_1m', '2026-09-30'));
    expect(back.filling).toBe(false);
    expect(back.profile?.poc).toBeCloseTo(p.poc);
    expect(back.profile?.up).toEqual(p.up);
    expect(back.profile?.valRow).toBe(p.valRow);
  });

  it('reads an empty answer as a stated null with the backend reason, never a zero profile', () => {
    const empty = wireToAnswer({
      schema_version: 1, enabled: true, histogram: [], poc: null, filling: true, feed: 'massive',
      error: "Reading 2026-09-29's 1-minute bars from the Massive files",
    });
    expect(empty).toEqual({
      profile: null, filling: true, error: "Reading 2026-09-29's 1-minute bars from the Massive files", feed: 'massive',
    });
  });

  it('asks for the kind, the day and the anchor, and words a refusal', async () => {
    novaFetch.mockResolvedValueOnce(new Response(JSON.stringify({ schema_version: 1, enabled: true, histogram: [] })));
    await fetchVolumeProfile('BRK.B', 'today', '2026-09-30', 1790869500.4, new AbortController().signal);
    const url = String(novaFetch.mock.calls[0][0]);
    expect(url).toContain('/api/volume-profile/BRK.B?');
    expect(url).toContain('kind=today');
    expect(url).toContain('day=2026-09-30');
    expect(url).toContain('anchor=1790869500');
    novaFetch.mockResolvedValueOnce(new Response(JSON.stringify({ detail: 'kind is today or yesterday' }), { status: 422 }));
    const refused = await fetchVolumeProfile('AAPL', 'yesterday', '2026-09-30', null, new AbortController().signal);
    expect(refused).toEqual({ profile: null, filling: false, error: 'Volume profile: kind is today or yesterday', feed: null });
  });
});
