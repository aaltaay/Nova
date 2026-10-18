/**
 * The 5-minute pane's volume profiles on the sample morning (ADR 058, `GET /api/volume-profile/{symbol}`): SMPL's
 * today from its own sample minutes, by the same method as the backend. The sample desk keeps no earlier day, so
 * yesterday's is a stated empty, as it is for every other symbol.
 */
import { buildProfile, profileToWire, type VolumeProfileWire } from '../../volume_profile';
import { SMPL } from './desk';
import { DAY, etMs } from './market';

export function sampleProfile(symbol: string, kind: string | null, anchor: string | null): VolumeProfileWire {
  const which = kind === 'yesterday' ? 'yesterday' : 'today';
  const empty = (error: string): VolumeProfileWire => ({
    schema_version: 1, enabled: true, symbol, kind: which, day: DAY, histogram: [], filling: false, error,
  });
  if (which === 'yesterday') return empty('the sample desk keeps no earlier day');
  if (symbol !== 'SMPL') return empty('the sample desk has 1-minute bars for SMPL only');
  const from = anchor ? Number(anchor) : etMs(9, 30) / 1000;
  const bars = SMPL.minute.map((b) => ({ t: b.t / 1000, o: b.o, h: b.h, l: b.l, c: b.c, v: b.v }));
  const p = buildProfile(bars, from, etMs(20, 0) / 1000);
  return p ? profileToWire(symbol, 'today', p, 'bars_1m', DAY) : empty('no 1-minute bars since the anchor yet');
}
