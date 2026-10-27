/**
 * The pop-up's sound state: the "Sound on switch" switch, today's muted stocks, the chime for a switch on
 * the list on screen and the beeps for a halt there. A halt is compared with the last board of the same
 * list and source; the first board after opening, a list change or a live <-> Sim change beeps nothing. A pop-up
 * left open past 04:00 ET drops yesterday's mutes the first time it next decides a sound.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { deskTradingDay } from '../utils/deskTradingDay';
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
  const mutedDay = useRef(deskTradingDay(Date.now()));
  const haltSeen = useRef<HaltSeen | null>(null);

  useEffect(() => {
    window.addEventListener('pointerdown', unlockTopNineAudio, { once: true });
    return () => window.removeEventListener('pointerdown', unlockTopNineAudio);
  }, []);

  // Today's mutes: a new desk day reads the stored list again, which holds none of yesterday's.
  const currentMuted = useCallback((): ReadonlySet<string> => {
    const now = Date.now();
    const today = deskTradingDay(now);
    if (today !== mutedDay.current) {
      mutedDay.current = today;
      mutedRef.current = readTopNineMuted(now);
      setMuted(mutedRef.current);
    }
    return mutedRef.current;
  }, []);

  const onSwitch = useCallback((switchedList: TopNineList, switched: TopNineSwitch) => {
    if (switchedList === listRef.current && chimeWorthy(switched, currentMuted())) chimeTopNine(soundRef.current);
  }, [currentMuted]);

  useEffect(() => {
    if (!snapshot) return;
    const rows = snapshot.lists[list].rows;
    const prev = haltSeen.current;
    const same = prev && prev.list === list && prev.kind === snapshot.source.kind;
    haltSeen.current = { list, kind: snapshot.source.kind, symbols: haltedSymbols(rows) };
    const muted = currentMuted();
    if (same && newlyHalted(prev.symbols, rows, muted).length) beepTopNineHalt(soundRef.current);
  }, [snapshot, list, currentMuted]);

  const chooseSound = useCallback((on: boolean) => {
    writeTopNineSound(on);
    setSound(on);
  }, []);

  const toggleMute = useCallback((symbol: string) => {
    const now = Date.now();
    const next = new Set(readTopNineMuted(now));
    if (next.has(symbol)) next.delete(symbol);
    else next.add(symbol);
    writeTopNineMuted(next, now);
    mutedDay.current = deskTradingDay(now);
    mutedRef.current = next;
    setMuted(next);
  }, []);

  return { sound, chooseSound, muted, toggleMute, onSwitch };
}
