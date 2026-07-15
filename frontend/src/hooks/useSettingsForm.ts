/**
 * Settings form state + GET/POST /api/config.
 * Extracted from App.tsx so the dashboard page stays focused on layout.
 */
import { useCallback, useRef, useState } from 'react';
import {
  API_URL,
  DATA_FEED_DEFAULT,
  DISCOVERY_PROVIDER_DEFAULT,
} from '../constants';

export function useSettingsForm(onSaved?: () => void) {
  const onSavedRef = useRef(onSaved);
  onSavedRef.current = onSaved;

  const [showSettings, setShowSettings] = useState(false);
  const [apiKey, setApiKey] = useState('');
  const [apiSecret, setApiSecret] = useState('');
  const [baseUrl, setBaseUrl] = useState('https://api.alpaca.markets');
  const [dataFeed, setDataFeed] = useState(DATA_FEED_DEFAULT);
  const [dataFeedOptions, setDataFeedOptions] = useState<string[]>(['iex', 'sip']);
  const [discoveryProvider, setDiscoveryProvider] = useState(DISCOVERY_PROVIDER_DEFAULT);
  const [discoveryProviderOptions, setDiscoveryProviderOptions] = useState<string[]>([
    'alpaca',
    'ibkr',
  ]);
  const [activeFeed, setActiveFeed] = useState(DATA_FEED_DEFAULT);
  const [feedFellBack, setFeedFellBack] = useState(false);

  const fetchConfig = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/config`);
      if (!res.ok) return;
      const data = await res.json();
      setApiKey(data.api_key);
      setApiSecret(data.api_secret);
      setBaseUrl(data.base_url);
      if (data.data_feed) {
        setDataFeed(data.data_feed);
        setActiveFeed(data.data_feed);
      }
      if (Array.isArray(data.data_feed_options)) setDataFeedOptions(data.data_feed_options);
      if (data.discovery_provider) setDiscoveryProvider(data.discovery_provider);
      if (Array.isArray(data.discovery_provider_options)) {
        setDiscoveryProviderOptions(data.discovery_provider_options);
      }
    } catch {
      // silent
    }
  }, []);

  const handleConfigUpdate = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const res = await fetch(`${API_URL}/config`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          api_key: apiKey,
          api_secret: apiSecret,
          base_url: baseUrl,
          data_feed: dataFeed,
          discovery_provider: discoveryProvider,
        }),
      });
      if (res.ok) {
        const result = await res.json();
        if (result.data_feed) setActiveFeed(result.data_feed);
        if (result.discovery_provider) setDiscoveryProvider(result.discovery_provider);
        setFeedFellBack(false);
        setShowSettings(false);
        onSavedRef.current?.();
      }
    } catch {
      alert('Error updating configuration');
    }
  };

  return {
    showSettings,
    setShowSettings,
    apiKey,
    setApiKey,
    apiSecret,
    setApiSecret,
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
