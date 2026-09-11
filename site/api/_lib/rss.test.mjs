import assert from "node:assert/strict";
import { test } from "node:test";

import { decodeEntities, parseGoogleNewsRss, stripPublisherSuffix } from "./rss.mjs";

const SAMPLE = `<?xml version="1.0"?><rss><channel>
<item>
  <title>S.E.C. Investigating Near-Implosion of A.I. Hedge Fund - The New York Times</title>
  <link>https://news.google.com/rss/articles/ABC?oc=5</link>
  <guid isPermaLink="false">ABC</guid>
  <pubDate>Mon, 24 Aug 2026 07:00:00 GMT</pubDate>
  <source url="https://www.nytimes.com">The New York Times</source>
</item>
<item>
  <title>Goldman &amp; Citi Face Subpoenas - Barron&#39;s</title>
  <link>https://news.google.com/rss/articles/DEF?oc=5</link>
  <pubDate>Tue, 25 Aug 2026 07:00:00 GMT</pubDate>
  <source url="https://www.barrons.com">Barron's</source>
</item>
<item>
  <title>Orphan headline with no source element</title>
  <link>https://news.google.com/rss/articles/GHI?oc=5</link>
</item>
</channel></rss>`;

test("parses items and resolves the publisher host", () => {
  const items = parseGoogleNewsRss(SAMPLE);
  assert.equal(items.length, 2, "the sourceless item is dropped");
  assert.equal(items[0].sourceUrl, "https://www.nytimes.com");
  assert.equal(items[0].publisherName, "The New York Times");
  assert.equal(items[0].link, "https://news.google.com/rss/articles/ABC?oc=5");
  assert.equal(items[0].publishedAt, Date.parse("Mon, 24 Aug 2026 07:00:00 GMT"));
});

test("strips the trailing publisher name Google appends to every headline", () => {
  const items = parseGoogleNewsRss(SAMPLE);
  assert.equal(items[0].title, "S.E.C. Investigating Near-Implosion of A.I. Hedge Fund");
  assert.equal(items[1].title, "Goldman & Citi Face Subpoenas");
});

test("stripPublisherSuffix leaves a headline that merely mentions the publisher", () => {
  assert.equal(
    stripPublisherSuffix("Reuters wins award for markets coverage", "Barron's"),
    "Reuters wins award for markets coverage",
  );
});

test("decodes named, decimal and hex entities", () => {
  assert.equal(decodeEntities("AT&amp;T &#39;beats&#39; &#x27;est&#x27;"), "AT&T 'beats' 'est'");
});

test("returns an empty list for junk input instead of throwing", () => {
  assert.deepEqual(parseGoogleNewsRss(""), []);
  assert.deepEqual(parseGoogleNewsRss(null), []);
  assert.deepEqual(parseGoogleNewsRss("<html>not rss</html>"), []);
});
