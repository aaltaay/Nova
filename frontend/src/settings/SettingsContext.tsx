/**
 * AppShell-level Settings ownership: form, exchange filter, overlay open state.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  type ReactNode,
} from 'react';
import { SettingsWorkspace } from '../components/SettingsWorkspace';
import { useExchangeFilter, type ExchangeFilter } from '../hooks/useExchangeFilter';
import { useSettingsForm } from '../hooks/useSettingsForm';

type SettingsForm = ReturnType<typeof useSettingsForm>;

interface SettingsContextValue {
  settings: SettingsForm;
  exchangeFilter: ExchangeFilter;
  openSettings: () => void;
  closeSettings: () => void;
  toggleSettings: () => void;
  registerOnConfigSaved: (fn: () => void) => void;
}

const SettingsContext = createContext<SettingsContextValue | null>(null);

export function SettingsProvider({ children }: { children: ReactNode }) {
  const onSavedRef = useRef<() => void>(() => {});
  const settings = useSettingsForm(() => onSavedRef.current());
  const exchangeFilter = useExchangeFilter();
  const { showSettings, setShowSettings, fetchConfig } = settings;

  const registerOnConfigSaved = useCallback((fn: () => void) => {
    onSavedRef.current = fn;
  }, []);

  const openSettings = useCallback(() => {
    setShowSettings(true);
  }, [setShowSettings]);

  const closeSettings = useCallback(() => {
    setShowSettings(false);
  }, [setShowSettings]);

  const toggleSettings = useCallback(() => {
    setShowSettings((s) => !s);
  }, [setShowSettings]);

  useEffect(() => {
    if (showSettings) void fetchConfig();
  }, [showSettings, fetchConfig]);

  const value = useMemo(
    () => ({
      settings,
      exchangeFilter,
      openSettings,
      closeSettings,
      toggleSettings,
      registerOnConfigSaved,
    }),
    [
      settings,
      exchangeFilter,
      openSettings,
      closeSettings,
      toggleSettings,
      registerOnConfigSaved,
    ],
  );

  return (
    <SettingsContext.Provider value={value}>
      {children}
      {showSettings && (
        <SettingsWorkspace
          filter={exchangeFilter}
          apiKey={settings.apiKey}
          onApiKeyChange={settings.setApiKey}
          apiSecret={settings.apiSecret}
          onApiSecretChange={settings.setApiSecret}
          apiKeySet={settings.apiKeySet}
          apiSecretSet={settings.apiSecretSet}
          baseUrl={settings.baseUrl}
          onBaseUrlChange={settings.setBaseUrl}
          dataFeed={settings.dataFeed}
          onDataFeedChange={settings.setDataFeed}
          dataFeedOptions={settings.dataFeedOptions}
          discoveryProvider={settings.discoveryProvider}
          onSubmit={settings.handleConfigUpdate}
          onCancel={closeSettings}
        />
      )}
    </SettingsContext.Provider>
  );
}

export function useSettings(): SettingsContextValue {
  const ctx = useContext(SettingsContext);
  if (!ctx) {
    throw new Error('useSettings must be used within SettingsProvider');
  }
  return ctx;
}

/** Safe when SampleShell (or tests) omit the provider. */
export function useSettingsOptional(): SettingsContextValue | null {
  return useContext(SettingsContext);
}
