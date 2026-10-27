/**
 * The pop-up's sound state: the "Sound on switch" switch, today's muted stocks, the chime for a switch on
 * the list on screen and the beeps for a halt there. A halt is compared with the last board of the same
 * list and source; the first board after opening, a list change or a live <-> Sim change beeps nothing.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import type { TopNineList } from './topNineConstants';
import { chimeWorthy, haltedSymbols, newlyHalted, readTopNineMuted, writeTopNineMuted } from './topNineAlerts';
import type { TopNineSwitch } from './topNineMarks';
import type { TopNineSnapshot } from './topNineSnapshot';
import { beepTopNineHalt, chimeTopNine, readTopNineSound, unlockTopNineAudio, writeTopNineSound } from './topNineSound';

interface HaltSeen {
  list: TopNineList;
  kind: string;
  symbols: Set<string>;
}

export function useTopNineAlerts(list: TopNineList, snapshot: TopNineSnapshot | null) {
  const [sound, setSound] = useState(() => readTopNineSound());
  const [muted, setMuted] = useState(() => readTopNineMuted());
  const listRef = useRef(list);
  listRef.current = list;
  const soundRef = useRef(sound);
  soundRef.current = sound;
  const mutedRef = useRef(muted);
  mutedRef.current = muted;
  const haltSeen = useRef<HaltSeen | null>(null);

  useEffect(() => {
    window.addEventListener('pointerdown', unlockTopNineAudio, { once: true });
    return () => window.removeEventListener('pointerdown', unlockTopNineAudio);
  }, []);

  const onSwitch = useCallback((switchedList: TopNineList, switched: TopNineSwitch) => {
    if (switchedList === listRef.current && chimeWorthy(switched, mutedRef.current)) chimeTopNine(soundRef.current);
  }, []);

  useEffect(() => {
    if (!snapshot) return;
    const rows = snapshot.lists[list].rows;
    const prev = haltSeen.current;
    const same = prev && prev.list === list && prev.kind === snapshot.source.kind;
    haltSeen.current = { list, kind: snapshot.source.kind, symbols: haltedSymbols(rows) };
    if (same && newlyHalted(prev.symbols, rows, mutedRef.current).length) beepTopNineHalt(soundRef.current);
  }, [snapshot, list]);

  const chooseSound = useCallback((on: boolean) => {
    writeTopNineSound(on);
    setSound(on);
  }, []);

  const toggleMute = useCallback((symbol: string) => {
    const next = new Set(readTopNineMuted());
    if (next.has(symbol)) next.delete(symbol);
    else next.add(symbol);
    writeTopNineMuted(next);
    setMuted(next);
  }, []);

  return { sound, chooseSound, muted, toggleMute, onSwitch };
}
