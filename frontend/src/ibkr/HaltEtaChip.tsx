/** LULD / halt reopen ETA chip for the Level 2 header (issue #173). */
import { useEffect, useState } from 'react';
import type { HaltSnapshot } from '../types/ticker';
import { haltChipView } from './haltEta';

interface Props {
  halt: HaltSnapshot | null | undefined;
  /** Test clock (unix ms). Live chip uses Date.now() and ticks once a second. */
  nowMs?: number;
}

export function HaltEtaChip({ halt, nowMs }: Props) {
  const [tick, setTick] = useState(() => Date.now());
  const live = nowMs == null;

  useEffect(() => {
    if (!live || !halt?.halted) return undefined;
    const id = window.setInterval(() => setTick(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [live, halt?.halted, halt?.halt_start, halt?.kind]);

  const view = haltChipView(halt, nowMs ?? tick);
  if (!view) return null;

  return (
    <span
      className={`sv-halt-eta-chip sv-halt-eta-chip--${view.kind}`}
      title={view.tooltip}
      data-testid="halt-eta-chip"
      data-kind={view.kind}
      data-phase={view.phase}
    >
      <span className="sv-halt-eta-chip__value">{view.label}</span>
    </span>
  );
}
