/**
 * Desk bus subscription for one OS window (ADR 011).
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { createTraderDeskBus, type TraderDeskBus } from './bus';
import type { TraderDeskRole } from './protocol';
import { traderDeskMessage } from './protocol';

export type TraderDockOffer = {
  symbol: string;
  sourceWindowId: string;
};

const DOCK_REQUEST_WAIT_MS = 450;

function newRequestId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return `dock-${Date.now()}`;
}

export function useTraderDesk(args: {
  windowId: string;
  role: TraderDeskRole;
  onDockRequest: (symbol: string, requestId: string, sourceWindowId: string) => boolean;
  onGaveTab: (symbol: string) => void;
  onDockRejected?: (symbol: string) => void;
  onDockUnanswered?: () => void;
}): {
  offer: TraderDockOffer | null;
  publishOffer: (symbol: string) => void;
  publishOfferEnd: () => void;
  requestDock: (symbol: string) => void;
  notifyDocked: (symbol: string, sourceWindowId: string) => void;
} {
  const { windowId, role, onDockRequest, onGaveTab, onDockRejected, onDockUnanswered } = args;
  const [offer, setOffer] = useState<TraderDockOffer | null>(null);
  const busRef = useRef<TraderDeskBus | null>(null);
  const onDockRequestRef = useRef(onDockRequest);
  const onGaveTabRef = useRef(onGaveTab);
  const onDockRejectedRef = useRef(onDockRejected);
  const onDockUnansweredRef = useRef(onDockUnanswered);
  const pendingDockRef = useRef<string | null>(null);
  onDockRequestRef.current = onDockRequest;
  onGaveTabRef.current = onGaveTab;
  onDockRejectedRef.current = onDockRejected;
  onDockUnansweredRef.current = onDockUnanswered;

  useEffect(() => {
    const bus = createTraderDeskBus();
    busRef.current = bus;
    const unsub = bus.subscribe((msg) => {
      if (msg.type === 'offer' && msg.symbol && msg.sourceWindowId !== windowId) {
        setOffer({ symbol: msg.symbol, sourceWindowId: msg.sourceWindowId });
        return;
      }
      if (msg.type === 'offer-end' && msg.sourceWindowId !== windowId) {
        setOffer(null);
        return;
      }
      if (
        msg.type === 'dock-request'
        && role === 'host'
        && msg.symbol
        && msg.requestId
        && msg.sourceWindowId !== windowId
      ) {
        const ok = onDockRequestRef.current(msg.symbol, msg.requestId, msg.sourceWindowId);
        bus.publish(traderDeskMessage(ok ? 'tab-docked' : 'dock-reject', {
          symbol: msg.symbol,
          sourceWindowId: msg.sourceWindowId,
          targetWindowId: windowId,
          requestId: msg.requestId,
        }));
        return;
      }
      if (msg.type === 'tab-docked' && msg.symbol && msg.sourceWindowId === windowId) {
        pendingDockRef.current = null;
        onGaveTabRef.current(msg.symbol);
        return;
      }
      if (msg.type === 'dock-reject' && msg.symbol && msg.sourceWindowId === windowId) {
        if (pendingDockRef.current == null) return;
        if (msg.requestId && pendingDockRef.current !== msg.requestId) return;
        pendingDockRef.current = null;
        onDockRejectedRef.current?.(msg.symbol);
      }
    });
    return () => {
      unsub();
      bus.close();
      if (busRef.current === bus) busRef.current = null;
    };
  }, [windowId, role]);

  const publishOffer = useCallback((symbol: string) => {
    busRef.current?.publish(traderDeskMessage('offer', {
      symbol,
      sourceWindowId: windowId,
    }));
  }, [windowId]);

  const publishOfferEnd = useCallback(() => {
    busRef.current?.publish(traderDeskMessage('offer-end', {
      sourceWindowId: windowId,
    }));
  }, [windowId]);

  const notifyDocked = useCallback((symbol: string, sourceWindowId: string) => {
    setOffer(null);
    busRef.current?.publish(traderDeskMessage('tab-docked', {
      symbol,
      sourceWindowId,
      targetWindowId: windowId,
    }));
  }, [windowId]);

  const requestDock = useCallback((symbol: string) => {
    const requestId = newRequestId();
    pendingDockRef.current = requestId;
    busRef.current?.publish(traderDeskMessage('dock-request', {
      symbol,
      sourceWindowId: windowId,
      requestId,
    }));
    window.setTimeout(() => {
      if (pendingDockRef.current === requestId) {
        pendingDockRef.current = null;
        onDockUnansweredRef.current?.();
      }
    }, DOCK_REQUEST_WAIT_MS);
  }, [windowId]);

  return { offer, publishOffer, publishOfferEnd, requestDock, notifyDocked };
}
