// Minimal Google News RSS reader.
//
// Deliberately regex-based rather than a DOM/XML dependency: the site ships with
// no package.json and no build step, and Google News RSS is a flat, stable
// <item> list -- title, link, pubDate, and a <source url="..."> that carries the
// publisher host the allowlist needs.

const ENTITIES = {
  amp: "&",
  lt: "<",
  gt: ">",
  quot: '"',
  apos: "'",
  nbsp: " ",
  "#39": "'",
  "#34": '"',
};

export function decodeEntities(value) {
  return String(value ?? "")
    .replace(/&(#x?[0-9a-f]+|[a-z]+);/gi, (match, code) => {
      const key = code.toLowerCase();
      if (key in ENTITIES) return ENTITIES[key];
      if (key.startsWith("#x")) {
        const point = Number.parseInt(key.slice(2), 16);
        return Number.isFinite(point) ? String.fromCodePoint(point) : match;
      }
      if (key.startsWith("#")) {
        const point = Number.parseInt(key.slice(1), 10);
        return Number.isFinite(point) ? String.fromCodePoint(point) : match;
      }
      return match;
    })
    .replace(/\s+/g, " ")
    .trim();
}

function tagText(block, tag) {
  const cdata = block.match(
    new RegExp(`<${tag}[^>]*><!\\[CDATA\\[([\\s\\S]*?)\\]\\]></${tag}>`, "i"),
  );
  if (cdata) return decodeEntities(cdata[1]);
  const plain = block.match(new RegExp(`<${tag}[^>]*>([\\s\\S]*?)</${tag}>`, "i"));
  return plain ? decodeEntities(plain[1]) : "";
}

/**
 * Google News renders headlines as "Real headline - Publisher Name".
 * The suffix is redundant next to the source badge, so drop the last one only
 * when it matches the publisher we already resolved.
 */
export function stripPublisherSuffix(title, publisherName) {
  if (!title || !publisherName) return title;
  const suffix = ` - ${publisherName}`;
  return title.endsWith(suffix) ? title.slice(0, -suffix.length).trim() : title;
}

/**
 * Parse a Google News RSS document into raw items.
 * Items missing a title, link, or resolvable source host are dropped -- the
 * allowlist cannot judge a story whose publisher is unknown.
 */
export function parseGoogleNewsRss(xml) {
  const items = [];
  for (const [, block] of String(xml ?? "").matchAll(/<item>([\s\S]*?)<\/item>/gi)) {
    const sourceUrl = block.match(/<source[^>]*url="([^"]+)"/i)?.[1] ?? "";
    const publisherName = tagText(block, "source");
    const rawTitle = tagText(block, "title");
    const link = tagText(block, "link");
    if (!rawTitle || !link || !sourceUrl) continue;

    const publishedAt = Date.parse(tagText(block, "pubDate"));
    items.push({
      title: stripPublisherSuffix(rawTitle, publisherName),
      link,
      sourceUrl,
      publisherName,
      publishedAt: Number.isFinite(publishedAt) ? publishedAt : null,
    });
  }
  return items;
}
