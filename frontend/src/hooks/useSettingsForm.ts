/**
 * Settings form state + GET/POST /api/config.
 * Scanner discovery is locked to IBKR — never posted as alpaca.
 */
import { useCallback, useRef, useState } from 'react';
import { novaFetch } from '../api/novaFetch';
import {
  API_URL,
  DATA_FEED_DEFAULT,
  DISCOVERY_PROVIDER_DEFAULT,
} from '../constants';
import { alertApp } from '../ux';

export function useSettingsForm(onSaved?: () => void) {
  const onSavedRef = useRef(onSaved);
  onSavedRef.current = onSaved;

  const [showSettings, setShowSettings] = useState(false);
  const [apiKey, setApiKey] = useState('');
  const [apiSecret, setApiSecret] = useState('');
  const [apiKeySet, setApiKeySet] = useState(false);
  const [apiSecretSet, setApiSecretSet] = useState(false);
  const [baseUrl, setBaseUrl] = useState('https://api.alpaca.markets');
  const [dataFeed, setDataFeed] = useState(DATA_FEED_DEFAULT);
  const [dataFeedOptions, setDataFeedOptions] = useState<string[]>(['iex', 'sip']);
  const [discoveryProvider, setDiscoveryProvider] = useState(DISCOVERY_PROVIDER_DEFAULT);
  const [discoveryProviderOptions, setDiscoveryProviderOptions] = useState<string[]>([
    DISCOVERY_PROVIDER_DEFAULT,
  ]);
  const [activeFeed, setActiveFeed] = useState(DATA_FEED_DEFAULT);
  const [feedFellBack, setFeedFellBack] = useState(false);

  const fetchConfig = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/config`);
      if (!res.ok) return;
      const data = await res.json();
      // SEC-001: GET returns masked secrets only — leave inputs empty for "keep existing".
      setApiKey('');
      setApiSecret('');
      setApiKeySet(Boolean(data.api_key_set));
      setApiSecretSet(Boolean(data.api_secret_set));
      setBaseUrl(data.base_url);
      if (data.data_feed) {
        setDataFeed(data.data_feed);
        setActiveFeed(data.data_feed);
      }
      if (Array.isArray(data.data_feed_options)) setDataFeedOptions(data.data_feed_options);
      // Product lock: always treat discovery as IBKR even if a stale payload arrives.
      setDiscoveryProvider(DISCOVERY_PROVIDER_DEFAULT);
      if (Array.isArray(data.discovery_provider_options)) {
        const opts = data.discovery_provider_options.filter(
          (p: string) => p === DISCOVERY_PROVIDER_DEFAULT,
        );
        setDiscoveryProviderOptions(opts.length ? opts : [DISCOVERY_PROVIDER_DEFAULT]);
      }
    } catch {
      // silent
    }
  }, []);

  const handleConfigUpdate = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const res = await novaFetch(`${API_URL}/config`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          // Empty string = keep existing secret on the server.
          api_key: apiKey,
          api_secret: apiSecret,
          base_url: baseUrl,
          data_feed: dataFeed,
          // Never send alpaca — server also coerces to ibkr.
          discovery_provider: DISCOVERY_PROVIDER_DEFAULT,
        }),
      });
      if (res.ok) {
        const result = await res.json();
        if (result.data_feed) setActiveFeed(result.data_feed);
        setDiscoveryProvider(DISCOVERY_PROVIDER_DEFAULT);
        setFeedFellBack(false);
        setShowSettings(false);
        onSavedRef.current?.();
      }
    } catch {
      void alertApp({
        title: 'Settings not saved',
        message: 'Error updating configuration. Check the API is running and try again.',
        tone: 'danger',
      });
    }
  };

  return {
    showSettings,
    setShowSettings,
    apiKey,
    setApiKey,
    apiSecret,
    setApiSecret,
    apiKeySet,
    apiSecretSet,
    baseUrl,
    setBaseUrl,
    dataFeed,
    setDataFeed,
    dataFeedOptions,
    discoveryProvider,
    setDiscoveryProvider,
    discoveryProviderOptions,
    activeFeed,
    setActiveFeed,
    feedFellBack,
    setFeedFellBack,
    fetchConfig,
    handleConfigUpdate,
  };
}
