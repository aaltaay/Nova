/**
 * An image from the feed, through Nova's backend. An `<img src>` cannot carry the desk's API key, so each image is
 * fetched with novaFetch into a blob URL, kept for reuse (the newest FOLLOWED_IMAGE_CACHE) and released when it
 * falls out. `version` asks again for an image that changes (a live slot). A missing image says so in words.
 */
import { useEffect, useState } from 'react';
import { novaFetch } from '../api/novaFetch';
import { API_BASE_URL } from '../constants';
import { FOLLOWED_IMAGE_CACHE } from './constants';

type ImageState = { url: string | null; failed: string | null };

const cache = new Map<string, string>();

function remember(key: string, url: string): void {
  cache.delete(key);
  cache.set(key, url);
  while (cache.size > FOLLOWED_IMAGE_CACHE) {
    const [oldKey, oldUrl] = cache.entries().next().value as [string, string];
    cache.delete(oldKey);
    URL.revokeObjectURL(oldUrl);
  }
}

export function resetFeedImagesForTests(): void {
  for (const url of cache.values()) URL.revokeObjectURL(url);
  cache.clear();
}

export function useFeedImage(path: string | null, version?: string | number | null): ImageState {
  const key = path === null ? null : version === undefined || version === null ? path : `${path}#${version}`;
  const [state, setState] = useState<ImageState>(() => ({ url: key ? cache.get(key) ?? null : null, failed: null }));
  useEffect(() => {
    if (!key || !path) {
      setState({ url: null, failed: null });
      return undefined;
    }
    const hit = cache.get(key);
    if (hit) {
      setState({ url: hit, failed: null });
      return undefined;
    }
    let cancelled = false;
    novaFetch(`${API_BASE_URL}${path}`)
      .then(async (res) => {
        if (!res.ok) throw new Error(res.status === 404 ? 'the feed has no such image' : `HTTP ${res.status}`);
        const url = URL.createObjectURL(await res.blob());
        remember(key, url);
        // A newer image replaces the one on screen only once it has arrived, so a live slot never blinks.
        if (!cancelled) setState({ url, failed: null });
      })
      .catch((e: unknown) => {
        if (!cancelled) setState((s) => ({ url: s.url, failed: e instanceof Error ? e.message : String(e) }));
      });
    return () => { cancelled = true; };
  }, [key, path]);
  return state;
}

interface Props {
  path: string | null;
  alt: string;
  className?: string;
  version?: string | number | null;
  missing?: string;
  testId?: string;
}

export function FeedImage({ path, alt, className, version, missing, testId }: Props) {
  const { url, failed } = useFeedImage(path, version);
  if (url) return <img src={url} alt={alt} className={className} data-testid={testId} />;
  const words = !path ? missing ?? null : failed ? `No image: ${failed}` : null;
  return (
    <span className={`ft-img-missing ${className ?? ''}`} data-testid={testId} role={words ? 'note' : undefined}>
      {words}
    </span>
  );
}
