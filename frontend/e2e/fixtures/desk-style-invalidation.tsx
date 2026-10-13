import { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogMedia, AlertDialogTitle,
} from '../../src/components/ui/alert-dialog';
import { PlaceOrderConfirmDialog } from '../../src/ibkr/PlaceOrderConfirmDialog';
import { TimeSalesView } from '../../src/ibkr/TimeSalesView';
import { appendTapePrint, type TapePrint } from '../../src/ibkr/tapeFeed';
import { TAPE_UI_MAX_ROWS } from '../../src/constants';
import '../../src/index.css';

// The Desk board row this fixture also drew is gone with the Desk (ADR 053);
// the tape, AlertDialog and order-confirmation guards stand.
const CANARY_COUNT = 500;
const PRINT_EVENT = 'desk-style-print';
const params = new URLSearchParams(location.search);
const size = params.get('size') === 'sm' ? 'sm' : 'default';
const media = params.get('media') === '1';

function print(serial: number): TapePrint {
  return { symbol: 'FIX', time: new Date(Date.UTC(2026, 9, 5, 13, 0, serial)).toISOString(),
    price: 6 + serial / 100, size: 100, exchange: 'NASDAQ', side: 'ask' };
}

function Tape() {
  const [prints, setPrints] = useState(() => Array.from({ length: TAPE_UI_MAX_ROWS }, (_, i) => print(-i)));
  const [count, setCount] = useState(0);
  useEffect(() => {
    let serial = 0;
    const append = () => {
      serial += 1;
      const next = print(serial);
      setPrints(previous => appendTapePrint(previous, next));
      setCount(serial);
    };
    window.addEventListener(PRINT_EVENT, append);
    return () => window.removeEventListener(PRINT_EVENT, append);
  }, []);
  return (
    <section style={{ display: 'flex', flexDirection: 'column', width: 320, height: 240, overflow: 'hidden' }}>
      <output data-testid="print-count">{count}</output>
      <TimeSalesView symbol="FIX" feed={{ prints, connected: true, error: null }} embedded />
    </section>
  );
}

function Fixture() {
  const [dialogOpen, setDialogOpen] = useState(false);
  const [orderOpen, setOrderOpen] = useState(false);
  const [confirmations, setConfirmations] = useState(0);
  return (
    <div className="nova-app-stack" style={{ display: 'block', padding: 20, overflow: 'auto' }}>
      <Tape />
      <div aria-hidden="true" style={{ position: 'absolute', width: 1, height: 1, overflow: 'hidden' }}>
        {Array.from({ length: CANARY_COUNT }, (_, i) => <span key={i} data-testid="style-canary">Canary {i}</span>)}
      </div>
      <button onClick={() => setDialogOpen(true)}>Open fixture dialog</button>
      <AlertDialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <AlertDialogContent size={size}>
          <AlertDialogHeader>
            {media && <AlertDialogMedia><span>Media</span></AlertDialogMedia>}
            <AlertDialogTitle>Fixture confirmation</AlertDialogTitle>
            <AlertDialogDescription>Fixture only; no order is sent.</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel fixture</AlertDialogCancel>
            <AlertDialogAction>Continue fixture</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
      <button onClick={() => setOrderOpen(true)}>Review practice order</button>
      <PlaceOrderConfirmDialog open={orderOpen} summary="BUY 10 FIX on Paper (fixture)"
        onCancel={() => setOrderOpen(false)}
        onConfirm={() => { setOrderOpen(false); setConfirmations(previous => previous + 1); }} />
      <output data-testid="order-confirmations">{confirmations}</output>
    </div>
  );
}

createRoot(document.getElementById('root')!).render(<Fixture />);
