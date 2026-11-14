/**
 * Nova on the phone (ADR 070): the desk's own providers -- account, settings, scanner -- under a
 * phone-shaped set of screens, with a workspace of the phone's own (PhoneWorkspace.tsx: no Trader tabs). The phone is a second screen, not a second system: every
 * number here is read by the hook the desk reads it with, and every write goes through the desk's
 * order door (`/api/phone`).
 */
import { useEffect, useState, type ReactNode } from 'react';
import { IbkrAccountProvider } from '../ibkr/IbkrAccountContext';
import { ScannerDataProvider } from '../scanner/ScannerDataContext';
import { SettingsProvider } from '../settings/SettingsContext';
import { LANDSCAPE, PORTRAIT, fitFor, useViewport } from './phoneFit';
import { ROUTE_EVENT, parseRoute, tabOf, type PhoneRoute } from './phoneRoute';
import { PhoneSessionProvider } from './PhoneSession';
import { PhoneWorkspaceProvider } from './PhoneWorkspace';
import { AccountScreen } from './screens/AccountScreen';
import { BookScreen } from './screens/BookScreen';
import { ChartScreen } from './screens/ChartScreen';
import { HomeScreen } from './screens/HomeScreen';
import { ScanScreen } from './screens/ScanScreen';
import { SettingsScreen } from './screens/SettingsScreen';
import { StockScreen } from './screens/StockScreen';
import { TopNineScreen } from './screens/TopNineScreen';
import { TradeScreen } from './screens/TradeScreen';

function usePhoneRoute(): PhoneRoute {
  const [route, setRoute] = useState<PhoneRoute>(() => parseRoute(window.location.hash));
  useEffect(() => {
    const read = () => setRoute(parseRoute(window.location.hash));
    window.addEventListener('hashchange', read);
    window.addEventListener('popstate', read);
    window.addEventListener(ROUTE_EVENT, read);
    return () => {
      window.removeEventListener('hashchange', read);
      window.removeEventListener('popstate', read);
      window.removeEventListener(ROUTE_EVENT, read);
    };
  }, []);
  return route;
}

function screenFor(route: PhoneRoute): ReactNode {
  switch (route.screen) {
    case 'scan': return <ScanScreen />;
    case 'top9': return <TopNineScreen />;
    case 'account': return <AccountScreen />;
    case 'settings': return <SettingsScreen />;
    case 'trade': return <TradeScreen symbol={route.symbol} />;
    case 'stock': return <StockScreen key={route.symbol} symbol={route.symbol} />;
    case 'chart': return <ChartScreen key={route.symbol} symbol={route.symbol} />;
    case 'book': return <BookScreen key={route.symbol} symbol={route.symbol} />;
    default: return <HomeScreen />;
  }
}

/** The page, shrunk as one piece when the viewport is smaller than the size its screen was drawn for. */
function PhoneFrame({ route, children }: { route: PhoneRoute; children: ReactNode }) {
  const viewport = useViewport();
  const sideways = viewport.width > viewport.height;
  const fit = fitFor(viewport, route.screen === 'chart' && sideways ? LANDSCAPE : PORTRAIT);
  return (
    <div
      className="ph-root"
      data-screen={route.screen}
      data-tab={tabOf(route) ?? 'none'}
      style={{ width: fit.width, height: fit.height, zoom: fit.zoom }}
    >
      {children}
    </div>
  );
}

export default function PhoneApp() {
  const route = usePhoneRoute();
  return (
    <PhoneWorkspaceProvider>
      <IbkrAccountProvider>
        <SettingsProvider>
          <ScannerDataProvider>
            <PhoneFrame route={route}>
              <PhoneSessionProvider>{screenFor(route)}</PhoneSessionProvider>
            </PhoneFrame>
          </ScannerDataProvider>
        </SettingsProvider>
      </IbkrAccountProvider>
    </PhoneWorkspaceProvider>
  );
}
