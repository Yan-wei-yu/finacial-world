import { test } from 'node:test';
import assert from 'node:assert/strict';
import { loadAll, mergeSnapshots, normalizeNews, normalizeQuotes, safeHttpUrl } from '../site/js/data.js';

test('safeHttpUrl only allows absolute http(s) links', () => {
  assert.equal(safeHttpUrl('https://example.com/a?b=1'), 'https://example.com/a?b=1');
  assert.equal(safeHttpUrl('javascript:alert(1)'), null);
  assert.equal(safeHttpUrl('data:text/html,hi'), null);
  assert.equal(safeHttpUrl('/relative'), null);
  assert.equal(safeHttpUrl(42), null);
});

test('normalizeNews drops malformed items and unsafe links', () => {
  const doc = normalizeNews({
    generated_at: '2026-10-15T13:00:00Z',
    categories: { semis: '半導體／AI' },
    items: [
      { id: 'a', title: 'ok', url: 'https://x.com', source: 'R', published: '2026-10-15T12:00:00Z', categories: ['semis'], symbols: [] },
      { id: 'b', title: 'bad link', url: 'javascript:void(0)', source: 'R', published: '2026-10-15T12:00:00Z' },
      { id: 'c', title: '', url: 'https://x.com', source: 'R', published: '2026-10-15T12:00:00Z' },
      null,
    ],
  });
  assert.deepEqual(doc.items.map((i) => i.id), ['a']);
  assert.deepEqual(doc.items[0].also, []);
  assert.equal(doc.categories.semis, '半導體／AI');
});

test('normalizeNews tolerates a missing document', () => {
  assert.deepEqual(normalizeNews(null).items, []);
});

test('normalizeQuotes guarantees holdings and quotes containers', () => {
  const doc = normalizeQuotes({ holdings: [{ symbol: 'NOK', shares: 820 }, { symbol: 7 }], quotes: null });
  assert.deepEqual(doc.holdings.map((h) => h.symbol), ['NOK']);
  assert.deepEqual(doc.quotes, {});
  assert.deepEqual(doc.market, []);
  assert.deepEqual(normalizeQuotes(undefined).holdings, []);
});

test('loadAll fetches every file and tolerates failures', async () => {
  const requested = [];
  const fakeFetch = async (url) => {
    requested.push(url);
    if (url.includes('summary')) return { ok: false, status: 404 };
    if (url.includes('macro')) throw new Error('network down');
    return { ok: true, status: 200, json: async () => ({ generated_at: 'x', items: [], holdings: [] }) };
  };

  const result = await loadAll('data/', fakeFetch);

  assert.equal(result.summary, null);
  assert.equal(result.macro, null);
  assert.ok(result.errors.some((e) => e.includes('macro')));
  assert.ok(!result.errors.some((e) => e.includes('summary')));
  assert.ok(requested.every((url) => url.startsWith('data/')));
  assert.equal(requested.length, 6);
});

test('loadAll reports which files failed (missing optional files are not failures)', async () => {
  const fakeFetch = async (url) => {
    if (url.includes('summary')) return { ok: false, status: 404 };
    if (url.includes('news')) return { ok: false, status: 503 };
    return { ok: true, status: 200, json: async () => ({ holdings: [] }) };
  };

  const result = await loadAll('data/', fakeFetch);

  assert.deepEqual(result.failed, ['news']);
});

test('only the frequently changing quote file is cache-busted', async () => {
  const requested = [];
  const fakeFetch = async (url, init) => {
    requested.push([url, init.cache]);
    return { ok: true, status: 200, json: async () => ({}) };
  };

  await loadAll('data/', fakeFetch);

  const byName = Object.fromEntries(requested.map(([url, cache]) => [url.split('/').pop().split('.')[0], { url, cache }]));
  assert.match(byName.quotes.url, /\?v=\d+$/);
  assert.equal(byName.news.url, 'data/news.json');
  assert.equal(byName.news.cache, 'no-cache');
});

test('mergeSnapshots keeps the previous document for files that failed', () => {
  const previous = { quotes: { holdings: [{ symbol: 'NOK', shares: 820 }] }, news: { items: [1] }, failed: [] };
  const next = { quotes: { holdings: [] }, news: { items: [2] }, failed: ['quotes'] };

  const merged = mergeSnapshots(previous, next);

  assert.deepEqual(merged.quotes, previous.quotes);
  assert.deepEqual(merged.news, next.news);
  assert.deepEqual(mergeSnapshots(null, next), next);
});
