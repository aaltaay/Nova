// Renders the "Signal" headline list from /api/ai-trading-news.
//
// Headlines are third-party text, so every string is written with textContent
// and every node is built by hand -- nothing from the feed reaches innerHTML.

(() => {
  const ENDPOINT = "/api/ai-trading-news";
  const list = document.getElementById("wire-list");
  const note = document.getElementById("wire-note");
  if (!list || !note) return;

  const MINUTE = 60_000;
  const HOUR = 60 * MINUTE;
  const DAY = 24 * HOUR;

  function relativeTime(iso) {
    if (!iso) return "";
    const then = Date.parse(iso);
    if (!Number.isFinite(then)) return "";
    const elapsed = Date.now() - then;
    if (elapsed < HOUR) return `${Math.max(1, Math.round(elapsed / MINUTE))}m ago`;
    if (elapsed < DAY) return `${Math.round(elapsed / HOUR)}h ago`;
    return `${Math.round(elapsed / DAY)}d ago`;
  }

  function element(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function renderItem(entry, index) {
    const row = element("li", "wire-item");
    row.dataset.tier = entry.tier ?? "";

    const link = element("a", "wire-link");
    link.href = entry.url;
    link.target = "_blank";
    link.rel = "noopener noreferrer";

    link.append(element("span", "wire-rank", String(index + 1).padStart(2, "0")));

    const body = element("span", "wire-body");
    body.append(element("span", "wire-title", entry.title));

    const meta = element("span", "wire-meta");
    meta.append(element("span", "wire-pub", entry.publisher || entry.host || "Source"));
    const when = relativeTime(entry.published_at);
    if (when) {
      meta.append(element("span", "wire-dot", "\u00b7"));
      meta.append(element("span", "wire-time", when));
    }
    body.append(meta);

    link.append(body);
    row.append(link);
    return row;
  }

  function setState(state) {
    list.dataset.state = state;
    list.setAttribute("aria-busy", state === "loading" ? "true" : "false");
  }

  function showMessage(text) {
    list.replaceChildren();
    note.textContent = text;
  }

  function render(payload) {
    const items = Array.isArray(payload.items) ? payload.items : [];
    if (items.length === 0) {
      setState("empty");
      showMessage("No story cleared the quality bar in the last three weeks. The list refills on its own.");
      return;
    }

    setState("ready");
    list.replaceChildren(...items.map(renderItem));

    const checked = relativeTime(payload.fetched_at);
    const degraded = payload.status === "degraded" ? " Some sources did not answer this round." : "";
    note.textContent = `Curated from a vetted publisher list${checked ? `, checked ${checked}` : ""}.${degraded}`;
  }

  async function load() {
    try {
      const response = await fetch(ENDPOINT, { headers: { accept: "application/json" } });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      render(await response.json());
    } catch {
      setState("error");
      showMessage("The headline feed is unreachable right now. Nothing stale is being shown in its place.");
    }
  }

  load();
})();
