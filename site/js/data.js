/** Load the JSON snapshots written by the GitHub Actions pipeline and validate their shape. */

// Only quotes change every few minutes; the rest are revalidated with ETags (cache: 'no-cache').
const FILES = [
  { name: 'quotes', bust: true, optional: false },
  { name: 'news', bust: false, optional: false },
  { name: 'earnings', bust: false, optional: false },
  { name: 'macro', bust: false, optional: false },
  { name: 'summary', bust: false, optional: true },
  { name: 'meta', bust: false, optional: true },
];
const TIMEOUT_MS = 12000;

const isObj = (value) => value !== null && typeof value === 'object' && !Array.isArray(value);
const isStr = (value) => typeof value === 'string' && value.length > 0;
const list = (value) => (Array.isArray(value) ? value : []);
const strings = (value) => list(value).filter((v) => typeof v === 'string');

/** @param {unknown} value @returns {string|null} the URL when it is absolute http(s), else null */
export function safeHttpUrl(value) {
  if (typeof value !== 'string') return null;
  try {
    const url = new URL(value.trim());
    return url.protocol === 'https:' || url.protocol === 'http:' ? value.trim() : null;
  } catch {
    return null;
  }
}

/** @param {unknown} doc */
export function normalizeQuotes(doc) {
  const source = isObj(doc) ? doc : {};
  return {
    ...source,
    holdings: list(source.holdings).filter((h) => isObj(h) && isStr(h.symbol) && typeof h.shares === 'number'),
    quotes: isObj(source.quotes) ? source.quotes : {},
    market: list(source.market).filter(isObj),
    indicators: list(source.indicators).filter(isObj),
    fx: isObj(source.fx) ? source.fx : {},
    errors: strings(source.errors),
  };
}

/** @param {unknown} doc */
export function normalizeNews(doc) {
  const source = isObj(doc) ? doc : {};
  const items = list(source.items)
    .filter((it) => isObj(it) && isStr(it.id) && isStr(it.title) && isStr(it.published) && safeHttpUrl(it.url))
    .map((it) => ({
      ...it,
      categories: strings(it.categories),
      symbols: strings(it.symbols),
      also: list(it.also).filter((a) => isObj(a) && isStr(a.source) && safeHttpUrl(a.url)),
    }));
  return {
    generated_at: isStr(source.generated_at) ? source.generated_at : null,
    categories: isObj(source.categories) ? source.categories : {},
    items,
    feed_errors: isObj(source.feed_errors) ? source.feed_errors : {},
  };
}

function normalizeEarnings(doc) {
  if (!isObj(doc)) return null;
  return {
    ...doc,
    upcoming: list(doc.upcoming).filter((e) => isObj(e) && isStr(e.symbol) && isStr(e.date)),
    recent: list(doc.recent).filter((e) => isObj(e) && isStr(e.symbol) && isStr(e.date)),
    history: isObj(doc.history) ? doc.history : {},
  };
}

function normalizeMacro(doc) {
  if (!isObj(doc)) return null;
  return {
    ...doc,
    week: list(doc.week).filter((e) => isObj(e) && isStr(e.datetime) && isStr(e.title)),
    upcoming: list(doc.upcoming).filter((e) => isObj(e) && isStr(e.date) && isStr(e.title)),
  };
}

function normalizeSummary(doc) {
  if (!isObj(doc) || !isStr(doc.headline)) return null;
  return { ...doc, key_points: list(doc.key_points).filter(isObj), holdings: list(doc.holdings).filter(isObj), watch_next: list(doc.watch_next).filter(isObj) };
}

async function fetchJson(base, file, fetchImpl, version) {
  const { name, bust, optional } = file;
  const controller = typeof AbortController === 'function' ? new AbortController() : null;
  const timer = controller ? setTimeout(() => controller.abort(), TIMEOUT_MS) : null;
  try {
    const url = `${base}${name}.json${bust ? `?v=${version}` : ''}`;
    const response = await fetchImpl(url, { cache: bust ? 'no-store' : 'no-cache', signal: controller?.signal });
    if (!response.ok) {
      const optionalMissing = optional && response.status === 404;
      return { data: null, error: optionalMissing ? null : `${name}: HTTP ${response.status}` };
    }
    return { data: await response.json(), error: null };
  } catch (error) {
    return { data: null, error: `${name}: ${error instanceof Error ? error.message : String(error)}` };
  } finally {
    if (timer) clearTimeout(timer);
  }
}

/**
 * Fetch every snapshot in parallel. A failing file never blocks the others.
 * @param {string} [base] @param {typeof fetch} [fetchImpl] @param {number} [now]
 */
export async function loadAll(base = 'data/', fetchImpl = (...args) => globalThis.fetch(...args), now = Date.now()) {
  const version = Math.floor(now / 60000);
  const results = await Promise.all(FILES.map((file) => fetchJson(base, file, fetchImpl, version)));
  const data = Object.fromEntries(FILES.map((file, index) => [file.name, results[index].data]));
  return {
    quotes: normalizeQuotes(data.quotes),
    news: normalizeNews(data.news),
    earnings: normalizeEarnings(data.earnings),
    macro: normalizeMacro(data.macro),
    summary: normalizeSummary(data.summary),
    meta: isObj(data.meta) ? data.meta : null,
    errors: results.map((r) => r.error).filter(Boolean),
    failed: FILES.filter((_, index) => results[index].error).map((file) => file.name),
  };
}

/** Keep the last good document for every file that failed this time (a flaky poll must not blank the page). */
export function mergeSnapshots(previous, next) {
  if (!previous) return next;
  const merged = { ...next };
  for (const name of next.failed ?? []) {
    if (name in previous) merged[name] = previous[name];
  }
  return merged;
}
